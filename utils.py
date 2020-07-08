import json
import urllib.request

import psutil

def _format_json(dictionary):
    return json.dumps(dictionary, indent=4, sort_keys=True)

def _internet_on():
    try:
        urllib.request.urlopen('http://www.google.com', timeout=1)
        return True
    except (urllib.error.URLError, socket.timeout):
        return False

def _safe_remove(target):
    try:
        os.remove(target)
    except OSError:
        print("Did not find file!")

def _yes_or_no(question):
    while True:
        reply = str(input(question+' (y/n): ')).lower().strip()
        if reply[0] == 'y':
            return True
        else:
            print('You replied No.')
            return False

def _find_duplicate_processes(name):
    count = 0
    for proc in psutil.process_iter():
        if proc.name() == name:
            count = count + 1

    if count > 1:
        return True
    else:
        return False

def _kill_process(name):
    for proc in psutil.process_iter():
        if proc.name() == name and proc.pid != os.getpid():
            proc.kill()

def _find_cron(my_crontab, comment):
    if len(my_crontab) == 0:
        return False
    for job in my_crontab:
        if comment in str(job.comment):
            return True

def _config_cronjob(action, command=None, args=None, comment=None):
    my_crontab = CronTab(user=True)
    if action == "set":
        if utils._find_cron(my_crontab, comment):
            pass
        else:
            job = my_crontab.new(command='{} {}'.format(command, args), 
                        comment=comment)
            job.minute.every(1)
            my_crontab.write()
    elif action == "unset":
        if utils._find_cron(my_crontab, comment):
            for job in my_crontab:
                print("Removing ranger job")
                my_crontab.remove(job)
                my_crontab.write()
        else:
            print("Found no jobs")