#from time import sleep
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from os.path import isfile
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

class CarStatus:
    def __init__(self, batteryLevel: int, chargeStatus: str, charging: bool = False, lightsFlashSent: bool = False):
        self.batteryLevel = batteryLevel
        self.chargeStatus = chargeStatus
        self.charging = charging
        self.lightsFlashSent = lightsFlashSent

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

    if len(times) == 0:
        logger("No slots found")
        return False
    else:
        slots = (f"Current slots are:\n")
    
        for i,time in enumerate(times):
            slots += (f"Slot number: {i+1}\n")
            slots += (f"===============================\n")
            slots += (f"Start time: {time['startDt']}\n")
            slots += (f"End time: {time['endDt']}\n")
            slots += (f"===============================\n")

    logger(slots)

    timeNow = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/London"))
    
    #Check to see if the current time is in a slot
    inSlot = False
    for i,time in enumerate(times):
        slotStart = datetime.strptime(time['startDt'],'%Y-%m-%d %H:%M:%S%z').astimezone(ZoneInfo("Europe/London"))
        slotEnd = datetime.strptime(time['endDt'],'%Y-%m-%d %H:%M:%S%z').astimezone(ZoneInfo("Europe/London"))
        if(timeNow >= slotStart and timeNow <= slotEnd):
            inSlot = True

    return inSlot
    
async def checkCar(overrideSlot: bool = False, overrideFlashlights: bool = False):
    inSlot = checkSlot(apikey,accountNumber)
    if(inSlot or overrideSlot):
        if inSlot:
            logger("we are in a slot, checking car status... please wait.)")
        else:
            logger("we are not in a slot but override is true, checking car status... please wait.)")

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as websession:
            client = RenaultClient(websession=websession, locale="en_GB")
          
            await client.session.login(email, password)

            account = (await client.get_api_accounts())[0] #get first account
            vehicle = (await account.get_api_vehicles())[0] #get first vehicle     
            batteryStatus = await vehicle.get_battery_status()
            chargeStatus = batteryStatus.get_charging_status()
            chargeStatusReturn = "Unknown"
            charging = False
            lightsFlashSent = False

            logger(f"Current battery percent is : {str(batteryStatus.batteryLevel)}")

            if(chargeStatus == enums.ChargeState.WAITING_FOR_CURRENT_CHARGE):
                chargeStatusReturn = "Waiting for current charge";
                charging = False
                logger("Still waiting to charge.")
                logger(f"Start Lights to try and wake car: {await vehicle.start_lights()}")
                lightsFlashSent = True

            elif(chargeStatus == enums.ChargeState.CHARGE_IN_PROGRESS):
                chargeStatusReturn = "Charging";
                charging = True
                logger("We charging yay!!")
            elif(chargeStatus == enums.ChargeState.ENERGY_FLAP_OPENED or chargeStatus == enums.ChargeState.NOT_IN_CHARGE):
                chargeStatusReturn = "Car not plugged in";
                charging = False
                logger("Car not plugged in")
            else:
                logger(f"Unknown state: {chargeStatus}") 
            
            if overrideFlashlights:
                logger(f"Start Lights to try and wake car: {await vehicle.start_lights()}")
                lightsFlashSent = True
                

            return CarStatus(batteryLevel=batteryStatus.batteryLevel, chargeStatus=chargeStatusReturn, charging=charging, lightsFlashSent=lightsFlashSent)

def get_or_create_eventloop():
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError as ex:
        if "There is no current event loop in thread" in str(ex):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
        raise ex

    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop
        
def runLoop():
    loop = get_or_create_eventloop()
    if loop.is_running():
        loop.create_task(checkCar())
    else:
        loop.run_until_complete(checkCar())

runLoop()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.get("/api/check_car")   
async def check_car():
    carStatus = await checkCar(overrideSlot=True)
    return carStatus.__dict__

@app.get("/api/check_car_with_flashlights")   
async def check_car():
    carStatus = await checkCar(overrideSlot=True, overrideFlashlights=True)
    return carStatus.__dict__

@app.post("/api/clear_logs")
async def clear_logs():
    clearlogs()
    return True

@app.get("/api/job_status")
async def job_status():
    return settings.job_enabled

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
        return """
        <html>
        <head>
            <style>
                body {
                    background: #111;
                    color: orange;
                    font-family: 'Fira Mono', 'Consolas', 'Menlo', 'Monaco', 'Courier New', Courier, monospace;
                    font-size: 0.875rem;
                    margin: 0;
                    padding: 1em;
                }
            </style>
        </head>
        <body>""" + logcontent.replace("\n","<br />\n") + "</body></html>"
    else:
        return "<html><body>No logs</body></html>"
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


