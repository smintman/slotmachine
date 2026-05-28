# slot machine

## What is it?

Slot machine is automation for the Dacia spring and people using Octopus intelligent go tariff.

The Spring sometimes has issues going to sleep while waiting for a slot,
The service, runs and at set times checks octput api to see if user is in the slot
If they are then they we check to see if the car is charing, if not then it will flash the cars
lights.

<img width="795" height="638" alt="Screenshot 2026-05-28 at 19 50 55" src="https://github.com/user-attachments/assets/d58909a5-b923-471f-b8f9-22c91190b091" />


# set up

You need to set the following environment vars

```
export SM_Email=""
export SM_Password=""
export SM_OctAPI=""
export SM_OctAccNo=""
```

Email and password is the my dacia app username/passeword

The Oct API is the dev api key you can get from octopus website, and Oct acc no is your account number

Download the code

Then install the required dependencies that are in requirments.txt

This on linux is done using something like

pip install -r requirements.txt

# Running the service

To to terminal and run:

$ fastapi run app/main.py

This will run the application and give you a web address to access the logs

The address will be something like

http://0.0.0.0:8000/

This wil tell you what is had happened.

There are 2 buttons to control the system, Toggle Jobs will start/stop the job that are timed to check the charge status. By default this is set to check between 23:05 and 07:35 Every 30 mins.

When it program runs at these times system will check if there are any current slots and show something like this in the logs:

```
2025-11-16 22:41:35.895837 : Current slots are:
Slot number: 1
===============================
Start time: 2025-11-16 22:30:00+00:00
End time: 2025-11-16 23:00:00+00:00
===============================
Slot number: 2
===============================
Start time: 2025-11-17 02:30:00+00:00
End time: 2025-11-17 04:00:00+00:00
===============================
Slot number: 3
===============================
Start time: 2025-11-17 04:00:00+00:00
End time: 2025-11-17 04:30:00+00:00
===============================
```

If during one of these 30 min checks we are in an octoput slot, then it will then check if the car is charging, if not it will ask the car to flash its lights to try and wake up the car, or if the car is alrady charging it will tell you.

Clear logs button will clear the current saved logs.

# Docker image

A docker image that has been built as in ARM architecture to host on ARM based NAS or raspberry pi can be found
at docker.io smintman/slotmachine:latest

# Special thanks

To https://github.com/hacf-fr/renault-api as their library does most of the heavy lifting.. I've included a fork of their library in my solution for moment because it has issues working with the spring 2 car. I intend on raising this as PR in the future and replace my fork with a dependency.
