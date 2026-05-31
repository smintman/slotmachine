#from time import sleep
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from os.path import isfile
from renault_api.renault_client import RenaultClient
from renault_api.kamereon import enums
import os
import aiohttp
import asyncio
import json
from datetime import date, datetime,timezone,timedelta
from zoneinfo import ZoneInfo

email = os.environ['SM_Email']
password = os.environ['SM_Password']
apikey= os.environ['SM_OctAPI']
accountNumber= os.environ['SM_OctAccNo']

octopusGraphUrl = "https://api.octopus.energy/v1/graphql/"
logFileName = "data/slotmachine.log"
settingsFileName = "data/settings.json"

# Ensure the data folder exists before writing logs or settings
data_dir = os.path.dirname(logFileName)
os.makedirs(data_dir, exist_ok=True)

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
    with open(settingsFileName, "r") as f:
        data = json.load(f)
        return Settings(**data)

def saveSettings():
    with open(settingsFileName, "w") as f:
        return json.dump(settings.__dict__, f)

def logger(message):
    message = str(datetime.now()) + " : " + message + "\n"
    print(message)
    with open(logFileName, "a") as f:
        f.write(message)


scheduler = AsyncIOScheduler()
scheduler.start()
app = FastAPI()

def clearlogs():
     with open(logFileName, "w") as f:
        f.write("")

def startJobs():

    logger("Starting jobs")

    scheduler.add_job(checkCar, 'cron', 
                  day_of_week='*', 
                  hour='0-7', 
                  minute='05-35/30',id='job1')

    scheduler.add_job(checkCar, 'cron', 
                  day_of_week='*', 
                  hour='22-23', 
                  minute='05-35/30',id='job2')
    
def stopJobs():

    logger("Stopping jobs")
    if scheduler.get_job('job1') != None:
        scheduler.remove_job('job1')

    if scheduler.get_job('job2') != None:
        scheduler.remove_job('job2')

async def refreshToken(session, apikey):
    query = """
    mutation krakenTokenAuthentication($api: String!) {
    obtainKrakenToken(input: {APIKey: $api}) {
        token
    }
    }
    """
    variables = {'api': apikey}
    async with session.post(octopusGraphUrl, json={'query': query, 'variables': variables}) as response:
        response.raise_for_status()
        jsonResponse = await response.json()
        return jsonResponse['data']['obtainKrakenToken']['token']

async def getObject(session, authToken, accountNumber):
    query = """
        query getData($input: String!) {
            plannedDispatches(accountNumber: $input) {
                startDt
                endDt
            }
        }
    """
    variables = {'input': accountNumber}
    headers = {"Authorization": authToken}
    async with session.post(octopusGraphUrl, json={'query': query, 'variables': variables, 'operationName': 'getData'}, headers=headers) as response:
        response.raise_for_status()
        jsonResponse = await response.json()
        return jsonResponse['data']

async def getTimes(session, authToken, accountNumber):
    data = await getObject(session, authToken, accountNumber)
    return data['plannedDispatches']

async def checkSlot(session):
    logger(f"Checking slot information please wait.")

    try:
        #Get Token
        authToken = await refreshToken(session, apikey)
        times = await getTimes(session, authToken, accountNumber)
    except Exception as err:
        logger(f'Error checking Octopus slots: {err}')
        return False

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
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as websession:
        inSlot = await checkSlot(websession)
        if(inSlot or overrideSlot):
            if inSlot:
                logger("we are in a slot, checking car status... please wait.)")
            else:
                logger("we are not in a slot but override is true, checking car status... please wait.")

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
         
                if inSlot:
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
        else:
            logger("Not in a slot, skipping car check.")

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
async def check_car_with_flashlights():
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

@app.get("/api/logs", response_class=PlainTextResponse)
async def get_logs():
    if isfile(logFileName):
        with open(logFileName, "r") as f:
            return f.read()
    return ""
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
