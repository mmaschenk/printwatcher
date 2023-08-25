#!/bin/env -S python -u

import os
import yaml
import time
from datetime import datetime, timedelta
from prusalink import prusalink
import requests
import textwrap
import octorest
from dotenv import load_dotenv

load_dotenv()

apiToken = os.getenv('APITOKEN')
chatID = os.getenv('CHATID')
apiURL = f'https://api.telegram.org/bot{apiToken}/sendMessage'

def sendmessage(message):
    print(f"apitoken = [{apiToken}]. chatid = [{chatID}]. apiUrl = [{apiURL}]")
    response = requests.post(apiURL, json={
            'chat_id': chatID, 
            'parse_mode': "HTML",
            'text': message }
        )
    print(f"response = [{response.text}]")

class safedict(dict):
    def __getitem__(self, __key):
        #print(f"Getting: [{__key}] {len(__key)} {type(__key)}")
        #print(isinstance(__key,tuple))
        if isinstance(__key,tuple):
            try:
                val = super().__getitem__(__key[0])
                if isinstance(val, dict):
                    return safedict(dict)
                else:
                    return super().__getitem__(__key[0])
            except:
                return __key[1]
        else:
            try:
                val = super().__getitem__(__key)
                if val is None:
                    return safedict()
                else:
                    if isinstance(val,dict):
                        return safedict(val)
                    else:
                        return val
            except:
                return safedict()
        
    def __str__(self) -> str:
        return super().__str__() if len(self) else "None"
    
    def __repr__(self) -> str:
        return super().__repr__() if len(self) else "None"

def formatsecondduration(d):
    sec = d % 60
    minleft = d // 60
    min = minleft % 60
    hrs = minleft // 60
    return f"{hrs}:{min:02}:{sec:02}"

def debuglog(state):
    with open("debuglog", "a") as logfile:
        print(f"{datetime.now()}: {state}", file=logfile)

def protocol_prusalink(printerinfo, timeout=30):
    host = printerinfo['host']
    key = printerinfo['key']
    try:
        prusa = prusalink(host, key, port=80, timeout=timeout)
        printer = safedict(prusa.get_printer().json())
        job = safedict(prusa.get_job().json())
    
        debuglog( { 'printer': printer, 'job': job })
        print(f"printer = {printer}\njob = {job}")

        print(f"jobsprogress = {job['progress']} [{type(job)}] [{type(job['progress'])}]")
        state = {
            'printstate': 'printing' if job['state'] == 'Printing' else 'idle',
            'temperature': {
                'bed': printer['telemetry']['temp-bed'],
                'nozzle': printer['telemetry']['temp-nozzle'],
            },
            'targettemperature': {
                'bed': printer['temperature']['bed']['target'],
                'nozzle': printer['temperature']['tool0']['target'],
            },
            'z-height': printer['telemetry']['z-height'],
            'fulljobtime': job['job']['estimatedPrintTime'],
            'alreadyprinted': job['progress']['printTime', 0],
            'stillprinting': job['progress']['printTimeLeft', 0],
            'progress': job['progress']['completion', 0],
            'jobname': job['job']['file']['name','Unknown'],
        }
    except requests.exceptions.ConnectionError:
        state = {
            'printstate': 'unknown',
        }

    return state

def protocol_octoprint(printerinfo):
    url = printerinfo['url']
    key = printerinfo['key']

    try:
        client = octorest.OctoRest(url=url, apikey=key)

        cinfo = client.connection_info()
        print(cinfo)

        job =  safedict(client.job_info())
        print(f"job = {job}")

        printer = safedict(client.printer())
        print(f"printer = {printer}")

        state = {
            'printstate': 'printing' if printer['state']['flags']['printing'] else 'idle',
            'temperature': {
                'bed': printer['temperature']['bed']['actual'],
                'nozzle': printer['temperature']['tool0']['actual'],
            },
            'targettemperature': {
                'bed': printer['temperature']['bed']['target'],
                'nozzle': printer['temperature']['tool0']['target'],
            },
            'z-height': 'unknown',
            'fulljobtime': job['progress']['printTime', 0] + job['progress']['printTimeLeft', 0],
            'alreadyprinted': job['progress']['printTime', 0],
            'stillprinting': job['progress']['printTimeLeft', 0],
            'progress': job['progress']['completion', 0]/100,
            'jobname': job['job']['file']['name','Unknown'],
        }
    except:
        raise
        state = {
            'printstate': 'unknown',
        }
    return state

def init_states(settings):
    state = {}
    for m in settings:
        state[m['printer']] = 'idle'

    return state

def processtimes(status):
    _now = datetime.now()

    if 'stillprinting' in status:
        status['time_finished'] = (_now + timedelta(seconds=status['stillprinting'])).strftime('%H:%M')

    if 'alreadyprinted' in status:
        status['time_started'] = (_now - timedelta(seconds=status['alreadyprinted'])).strftime('%H:%M')

def statusmessage(headerline,status):
    processtimes(status)
    return textwrap.dedent(f"""
        <b>{headerline}</b>
        <pre>
        Printjob:            {status['jobname']}
        Z-Height:            {status['z-height']}
        Percentage complete: {status['progress']*100}
        Completion time:     {status['time_finished']} ({formatsecondduration(status['stillprinting'])} from now)
        Start time:          {status['time_started']} ({formatsecondduration(status['alreadyprinted'])} ago)
        Nozzle temperature:  {status['temperature']['nozzle']} / {status['targettemperature']['nozzle']}
        Bed temperature:     {status['temperature']['bed']} / {status['targettemperature']['bed']}
        </pre>
    """)


def main_loop(state, settings):
    messages = []
    for m in settings:
        print(f"Doing {m['printer']}")
        handler = f"protocol_{m['api']}"
        handler = globals()[handler]
        currentstate = handler(m)

        print(f"Current state: {currentstate}")

        debuglog(f"Current state: {currentstate}")

        print(f"currentstate: [{currentstate['printstate']}]. previous printstate: [{state[m['printer']]}]")
        if currentstate['printstate'] == 'printing' and state[m['printer']] == 'printing':    
            print("outputting ongoing print job")
            message = statusmessage(f"Printjob in progress on {m['printer']}", currentstate)
            messages.append(message)
            #sendmessage(message)
        elif currentstate['printstate'] == 'printing' and state[m['printer']] != 'printing':
            print(f"outputting start of print job {m['printer']}")
            message = statusmessage(f"Printjob started on {m['printer']}", currentstate)
            messages.append(message)
            #sendmessage(message)
        elif currentstate['printstate'] != 'printing' and state[m['printer']] == 'printing':
            print(f"outputting end of print job {m['printer']}")
            message = statusmessage(f"Printjob ended on {m['printer']}", currentstate)
            messages.append(message)
            #sendmessage(message)
        else:
            print("no messaging needed")

        state[m['printer']] = currentstate['printstate']

    if messages:
        message = "\n".join(messages)
        sendmessage(message)
        

def main():
    print(f"Opening {os.getenv('INPUTFILE')}")
    with open(os.getenv('INPUTFILE'),"r") as settingsfile:
        settings = yaml.safe_load(settingsfile)

    print(f"Settings: {settings}")

    state=init_states(settings=settings['printers'])

    while True:
        main_loop(state=state, settings=settings['printers'])
        print(f"state is now {state}")
        print(f"Sleeping for {settings['settings']['interval']} seconds")
        time.sleep(settings['settings']['interval'])

if __name__ == '__main__':
    main()