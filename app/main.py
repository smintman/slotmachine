#from time import sleep
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from apscheduler.schedulers.background import BackgroundScheduler
#from contextlib import asynccontextmanager
from datetime import datetime
from os.path import isfile
#from . import octopusSlots
from renault_api.renault_client import RenaultClient
from renault_api.kamereon import enums
import os
import aiohttp
import asyncio
import requests,json
from datetime import date, datetime,timezone,timedelta
from requests.models import HTTPError
from zoneinfo import ZoneInfo

email = os.environ['SM_Email']
password = os.environ['SM_Password']
apikey= os.environ['SM_OctAPI']
accountNumber= os.environ['SM_OctAccNo']

octopusGraphUrl = "https://api.octopus.energy/v1/graphql/"
logFileName = "slotmachine.log"
settingsFileName = "settings.json"

dateTimeToUse = datetime.now().astimezone()
if dateTimeToUse.hour < 17:
    dateTimeToUse = dateTimeToUse-timedelta(days=1)
ioStart = dateTimeToUse.astimezone().replace(hour=23, minute=30, second=0, microsecond=0)
ioEnd = dateTimeToUse.astimezone().replace(microsecond=0).replace(hour=5, minute=30, second=0, microsecond=0)+timedelta(days = 1)

class Settings:
    def __init__(self, job_enabled: bool):
        self.job_enabled = job_enabled

def loadSettings():
    with open("settings.json", "r") as f:
        data = json.load(f)
        return Settings(**data)

def saveSettings():
    with open("settings.json", "w") as f:
        return json.dump(settings.__dict__, f)

def logger(message):
    message = str(datetime.now()) + " : " + message + "\n"
    print(message)
    with open(logFileName, "a") as f:
        f.write(message)


scheduler = BackgroundScheduler()
scheduler.start()
app = FastAPI()

def clearlogs():
     with open(logFileName, "w") as f:
        f.write("")

def startJobs():

    logger("Starting jobs")

    scheduler.add_job(runLoop, 'cron', 
                  day_of_week='*', 
                  hour='0-7', 
                  minute='05-35/30',id='job1')

    scheduler.add_job(runLoop, 'cron', 
                  day_of_week='*', 
                  hour='23', 
                  minute='05-35/30',id='job2')
    
def stopJobs():

    logger("Stopping jobs")
    if scheduler.get_job('job1') != None:
        scheduler.remove_job('job1')

    if scheduler.get_job('job2') != None:
        scheduler.remove_job('job2')

def refreshToken(apikey):
    try:
        query = """
        mutation krakenTokenAuthentication($api: String!) {
        obtainKrakenToken(input: {APIKey: $api}) {
            token
        }
        }
        """

       
        variables = {'api': apikey}
        r = requests.post(octopusGraphUrl, json={'query': query , 'variables': variables})
    except HTTPError as http_err:
        logger(f'HTTP Error {http_err}')
    except Exception as err:
        logger(f'Another error occurred: {err}')

    jsonResponse = json.loads(r.text)
    #return jsonResponse
    return jsonResponse['data']['obtainKrakenToken']['token']

def getObject(authToken,apikey,accountNumber):
    try:
        query = """
            query getData($input: String!) {
                plannedDispatches(accountNumber: $input) {
                    startDt
                    endDt
                }
            }
        """
        variables = {'input': accountNumber}
        headers={"Authorization": authToken}
        r = requests.post(octopusGraphUrl, json={'query': query , 'variables': variables, 'operationName': 'getData'},headers=headers)
        return json.loads(r.text)['data']
    except HTTPError as http_err:
        logger(f'HTTP Error {http_err}')
    except Exception as err:
        logger(f'Another error occurred: {err}')

def getTimes(authToken,apikey,accountNumber):
    object = getObject(authToken,apikey,accountNumber)
    #print(object)
    return object['plannedDispatches']

def checkSlot(apikey,accountNumber):
    logger(f"Checking slot information please wait.")

    #Get Token
    authToken = refreshToken(apikey)
    times = getTimes(authToken,apikey,accountNumber)

    #Convert to the current timezone
    for i,time in enumerate(times):
        slotStart = datetime.strptime(time['startDt'],'%Y-%m-%d %H:%M:%S%z').astimezone(ZoneInfo("Europe/London"))
        slotEnd = datetime.strptime(time['endDt'],'%Y-%m-%d %H:%M:%S%z').astimezone(ZoneInfo("Europe/London"))
        time['startDt'] = str(slotStart)
        time['endDt'] = str(slotEnd)
        times[i] = time

    slots = (f"Current slots are:\n")
    
    for i,time in enumerate(times):
        
        slots += (f"Slot number: {i+1}\n")
        slots += (f"===============================\n")
        slots += (f"Start time: {time['startDt']}\n")
        slots += (f"End time: {time['endDt']}\n")
        slots += (f"===============================\n")

    logger(slots)
    #outputJsonString = json.dumps(times, indent=4, default=str)
    #print(outputJsonString)

    timeNow = datetime.now(timezone.utc).astimezone()

    #logger(f"The current time is: {timeNow}\n")

    #Check to see if the current time is in a slot
    inSlot = False
    for i,time in enumerate(times):
        slotStart = datetime.strptime(time['startDt'],'%Y-%m-%d %H:%M:%S%z').astimezone()
        slotEnd = datetime.strptime(time['endDt'],'%Y-%m-%d %H:%M:%S%z').astimezone()
        if(timeNow >= slotStart and timeNow <= slotEnd):
            inSlot = True

    return inSlot
       
async def checkCar():
    inSlot = checkSlot(apikey,accountNumber)
    if(inSlot):
        logger("In slot")
        async with aiohttp.ClientSession() as websession:

            logger(f"We are in a slot checking for charge status. please wait.")

            client = RenaultClient(websession=websession, locale="en_GB")
          
            await client.session.login(email, password)

            account = (await client.get_api_accounts())[0] #get first account
            vehicle = (await account.get_api_vehicles())[0] #get first vehicle     
            batteryStatus = await vehicle.get_battery_status()
            chargeStatus = batteryStatus.get_charging_status()

            logger(f"Current battery percent is : {str(batteryStatus.batteryLevel)}")

            if(chargeStatus == enums.ChargeState.WAITING_FOR_CURRENT_CHARGE):
                logger("Still waiting to charge.")
                logger(f"Start Lights to try and wake car: {await vehicle.start_lights()}")

            elif(chargeStatus == enums.ChargeState.CHARGE_IN_PROGRESS):
                logger("We charging yay!!")
            elif(chargeStatus == enums.ChargeState.ENERGY_FLAP_OPENED):
                logger("Car not plugged in")
            else:
                logger(f"Unknown state: {chargeStatus}") 
    else:
        logger("Not In slot")

def get_or_create_eventloop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError as ex:
        if "There is no current event loop in thread" in str(ex):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return asyncio.get_event_loop()
        else:
          raise ex
        
def runLoop():
    loop = get_or_create_eventloop()
    loop.run_until_complete(checkCar())

runLoop()



#scheduler.add_job(runLoop, 'interval', minutes=1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.post("/api/clear_logs")
async def clear_logs():
    clearlogs()
    return True

@app.post("/api/toggle_Job")
async def toggle_Job():
    if settings.job_enabled:
        settings.job_enabled = False
        saveSettings()
        stopJobs()
        return settings.job_enabled
    else:
        settings.job_enabled = True
        saveSettings()
        startJobs()
        return settings.job_enabled

@app.get("/api/logs", response_class=HTMLResponse)
async def logs():
    isFile = isfile(logFileName)
    if isFile:
        with open(logFileName, "r") as f:
            logcontent = f.read()
    else:
        logcontent = "No logs"

    return "<html><body>" + logcontent.replace("\n","<br />\n") + "</body></html>"

app.mount('/', StaticFiles(directory="./static", html=True), name="static")

if isfile(settingsFileName):
    #Load existings settings
    settings = loadSettings()

    if settings.job_enabled:
        startJobs()
else:
    #Create new default settings
    settings = Settings(job_enabled=True)
    startJobs()


