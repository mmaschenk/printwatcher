#!/bin/env -S python -u

import os
import yaml
import time
from datetime import datetime, timedelta
from prusalink import prusalink
import requests
import textwrap
import octorest
import traceback
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
    def getlayerplugindata(client):
        layer = f"{client.url}/plugin/DisplayLayerProgress/values"
        session = client.__dict__['session']
        
        r = requests.get(headers=session.headers, url=layer)
        return r.json()

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

        print(f"printerinfo = {printerinfo}")
        zheight = "unknown"
        if 'layerplugin' in printerinfo and printerinfo['layerplugin']:
            print("Getting layer info")
            data = getlayerplugindata(client=client)
            print(f"Got layerinfo {data}")
            try:
                zheight = f"{data['height']['current']} ({data['layer']['current']}/{data['layer']['total']})"
            except:
                try:
                    zheight = f"{data['height']['current']}"
                except:
                    pass

        try:
            printTime = job['progress']['printTime']
        except:
            printTime = 0

        try:
            printTimeLeft = int(job['progress']['printTimeLeft'])
        except:
            printTimeLeft = 0

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
            'z-height': zheight,
            'fulljobtime': printTime + printTimeLeft,
            'alreadyprinted': printTime,
            'stillprinting': printTimeLeft,
            'progress': job['progress']['completion', 0]/100,
            'jobname': job['job']['file']['name','Unknown'],
        }
    except Exception as exc:
        print(traceback.format_exc())
        print(exc)
        state = {
            'printstate': 'unknown',
        }
    return state

def init_states(settings):
    state = {}
    for m in settings:
        state[m['printer']] = { 'printstate': 'idle', 'lastsend': datetime.now() - timedelta(days=1) }

    return safedict(state)

def processtimes(status):
    _now = datetime.now()

    if 'stillprinting' in status:
        status['time_finished'] = (_now + timedelta(seconds=status['stillprinting'])).strftime('%H:%M')

    if 'alreadyprinted' in status:
        status['time_started'] = (_now - timedelta(seconds=status['alreadyprinted'])).strftime('%H:%M')

def statusmessage(headerline,status):
    processtimes(status)
    if 'stillprinting' not in status or status['stillprinting'] == 0:
        finishmessage = "-- Unknown --"
    else:
        finishmessage = f"{status['time_finished']} ({formatsecondduration(status['stillprinting'])} from now)"
    return textwrap.dedent(f"""
        <b>{headerline}</b>
        <pre>
        Printjob:    {status['jobname']}
        Z-Height:    {status['z-height']}
        % done:      {status['progress']*100:.1f}
        time to end: {finishmessage}
        Start time:  {status['time_started']} ({formatsecondduration(status['alreadyprinted'])} ago)
        Nozzle temp: {status['temperature']['nozzle']}\U000000B0 / {status['targettemperature']['nozzle']}\U000000B0
        Bed temp:    {status['temperature']['bed']}\U000000B0 / {status['targettemperature']['bed']}\U000000B0
        </pre>
    """)


def main_loop(state, settings, globalsettings):
    for m in settings:
        print(f"Doing {m['printer']}")
        handler = f"protocol_{m['api']}"
        handler = globals()[handler]
        limit = m['statusinterval']

        laststate = state[m['printer']]
        currentstate = laststate.copy()
        handleroutput = handler(m)
        currentstate.update(handleroutput)
        print(f"Current state: {currentstate}")
        debuglog(f"Current state: {currentstate}")

        print(f"current printstate: [{currentstate['printstate']}]. previous printstate: [{laststate['printstate']}]")
        forcemessage = False

        if currentstate['printstate'] == 'printing' and laststate['printstate'] == 'printing':    
            print("outputting ongoing print job")
            message = statusmessage(f"Printjob in progress on {m['printer']}", currentstate)
        elif currentstate['printstate'] == 'printing' and laststate['printstate'] != 'printing':
            forcemessage = True
            print(f"outputting start of print job {m['printer']}")
            message = statusmessage(f"Printjob started on {m['printer']}", currentstate)
        elif currentstate['printstate'] != 'printing' and laststate['printstate'] == 'printing':
            forcemessage = True
            print(f"outputting end of print job {m['printer']}")
            message = statusmessage(f"Printjob ended on {m['printer']}", currentstate)
            currentstate['cooldowntimeout'] = datetime.now() + timedelta(seconds=globalsettings['cooldowntimeout'])
        elif currentstate['printstate'] == 'idle' and laststate['printstate'] == 'idle' and 'cooldowntimeout' in currentstate:
            message = statusmessage(f"Cooling down on {m['printer']}", currentstate)
            if currentstate['cooldowntimeout'] < datetime.now():
                del currentstate['cooldowntimeout']
                message = statusmessage(f"Final cool down on {m['printer']}", currentstate)
        else:
            print("no messaging needed")
            # Break from rest of loop since no message needs to be sent
            continue

        try:
            timesincelastmessage = (datetime.now() - laststate['lastsend']).total_seconds()
        except Exception as exc:
            timesincelastmessage = -1

        laststate = currentstate
        print(f"Time since last: {timesincelastmessage}")
        if forcemessage or timesincelastmessage > limit:
            try:
                sendmessage(message=message)
                laststate['lastsend'] = datetime.now()
            except Exception as exc:
                print(traceback.format_exc())
                print(exc)

        state[m['printer']] = laststate


def main():
    print(f"Opening {os.getenv('INPUTFILE')}")
    with open(os.getenv('INPUTFILE'),"r") as settingsfile:
        settings = yaml.safe_load(settingsfile)

    print(f"Settings: {settings}")

    state=init_states(settings=settings['printers'])

    while True:
        main_loop(state=state, settings=settings['printers'], globalsettings=settings['settings'])
        print(f"state is now {state}")
        print(f"Sleeping for {settings['settings']['interval']} seconds")
        time.sleep(settings['settings']['interval'])

if __name__ == '__main__':
    main()