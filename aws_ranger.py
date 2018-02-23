import re
import os
import sys
import json
import socket
import difflib
import getpass
import time as Time

import urllib2
import smtplib

from crontab import CronTab
from datetime import time, date, timedelta, datetime

import boto3
import click
import psutil

from wryte import Wryte
from botocore.exceptions import ClientError

CURRENT_FILE = sys.argv[0]
USER_NAME = getpass.getuser()
USER_HOME = os.getenv("HOME")
HOST_NAME = socket.gethostname()
PUBLIC_IP = json.load(urllib2.urlopen('http://jsonip.com'))['ip']

AWS_RANGER_HOME = '{0}/.aws-ranger'.format(USER_HOME)
BOTO_CREDENTIALS = '{0}/.aws/credentials'.format(USER_HOME)

def _format_json(dictionary):
    return json.dumps(dictionary, indent=4, sort_keys=True)

def _internet_on():
    try:
        urllib2.urlopen('http://www.google.com', timeout=1)
        return True
    except urllib2.URLError as err: 
        return False
    except socket.timeout, e:
        return False

def _return_digits(string_input):
    return ''.join(i for i in string_input if i.isdigit())

def _safe_remove(target):
    try:
        os.remove(target)
    except OSError:
        print "Did not find file!"

def _yes_or_no(question):
    while True:
        reply = str(raw_input(question+' (y/n): ')).lower().strip()
        if reply[0] == 'y':
            return True
        else:
            print 'You replied No.'
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
        if _find_cron(my_crontab, comment):
            pass
        else:
            job = my_crontab.new(command='{} {}'.format(command, args), 
                        comment=comment)
            job.minute.every(1)
            my_crontab.write()
    elif action == "unset":
        if _find_cron(my_crontab, comment):
            for job in my_crontab:
                print "Removing aws-ranger job"
                my_crontab.remove(job)
                my_crontab.write()
        else:
            print "Found no jobs"

def validate_ranger(ranger_home, config_path):
    if not os.path.exists(ranger_home):
        print ' Missing aws-ranger HOME dir...\n Run:\n'\
              ' aws-ranger --init or create it yourself at ~/.aws-ranger'
        sys.exit()
    
    if not os.path.exists(config_path):
        print ' Missing aws-ranger config...\n Run:\n'\
              ' aws-ranger --init '
        sys.exit()

def working_hours_converter(target):
    if target[0].isdigit() and 0 < int(target[0]) < 13:
        return target

    days = ["Sunday", "Sun", "Monday", "Mon",
            "Thursday", "Thu", "Friday", "Fri"]
    for day in days:
        if difflib.SequenceMatcher(None,a=target.lower(),b=day).ratio() > 0.8:
            return day

def create_config_file(config_path, profile_name="default"):
    # wryter = Wryte(name='aws-ranger')
    aws_ranger_config = {}
    email_dictionary = {}
    
    # Config section

    # Tags
    default_exclude_tags = ["prod", "production", "free range"]
    tags_text = '\nPlease enter tag values to exclude them '\
            'from aws-ranger (use comma to separate items) '\
            '\nDefaults = [prod, production, free range]: '
    exclude_tags = raw_input(tags_text).split(",")
    if len(exclude_tags) == 0:
        exclude_tags = default_exclude_tags
    aws_ranger_config["EXCLUDE_TAGS"] = exclude_tags

    # Working Hours
    default_working_hours = {"First Day of the Week": "Sunday",
                             "Last Day of the week": "Thursday",
                             "Start of working Day": "9AM",
                             "End of working Day": "6PM"}
    if _yes_or_no('\nDo you agree with these working hours? '\
                  '\n{} '.format(_format_json(default_working_hours))):
        working_hours = default_working_hours
        aws_ranger_config["Working Hours"] = working_hours
    else:
        first_day = working_hours_converter(
            raw_input("First Day of the Week? : "))
        last_day = working_hours_converter(
            raw_input("\nLast Day of the week? : "))
        start_of_day = working_hours_converter(
            raw_input("Start of working day? : "))
        end_of_day = working_hours_converter(
            raw_input("End of working day? (12H format) : "))
        
        working_hours = {"First Day of the Week": first_day,
                         "Last Day of the week": last_day,
                         "Start of working Day": '{}AM'.format(
                             start_of_day),
                         "End of working Day": '{}PM'.format(
                             end_of_day)}
        aws_ranger_config["Working Hours"] = working_hours

    # Email section
    email_dictionary['GMAIL_ACCOUNT'] = raw_input("\nGmail account? ")
    email_dictionary['GMAIL_PASSWORD'] = raw_input("Gmail password? ")
    email_dictionary['DESTINATION_EMAIL'] = raw_input(
        "Notification Destination? ")
    aws_ranger_config["EMAIL"] = email_dictionary
    
    with open(config_path, 'w') as file:
        json.dump(aws_ranger_config, file, indent=4)

def read_json_file_section(config_path, 
                           requested_data, 
                           profile_name="default"):
    ranger_config = json.load(open(config_path))
    return ranger_config[requested_data]

def send_mail(config_path, subject, msg):
    email_config = read_json_file_section(config_path, "EMAIL")
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(email_config["GMAIL_ACCOUNT"], 
                 email_config["GMAIL_PASSWORD"])

    server.sendmail(email_config["GMAIL_ACCOUNT"], 
                    email_config["DESTINATION_EMAIL"],
                    'Subject: {}\n\n{}'.format(subject, msg))
    server.quit()
    
def find_profiles(file):
    profiles_list = []
    boto_config = open(file).read()
    for match in re.findall("\[.*\]", boto_config):
        profiles_list.append(match.strip("[]"))
    return profiles_list
        
def create_short_instances_dict(all_instances_dictionary, execute_action, service=False):
    instance_dict ={}

    for region in all_instances_dictionary.items():
        instances_ids_list = []
        stopped_instances_ids = []
        running_instances_ids = []
        managed_instances_ids = []
        try:
            if region[1] in ["running", "stopped", "exclude", "managed"]:
                pass
        except KeyError:
            region[1]["Region State"] = "Region vacent"
        
        for state in region[1]:
            if state == "managed":
                for instance in region[1][state]:
                    managed_instances_ids.append(instance["_ID"])
            
            if state == "running":
                for instance in region[1][state]:
                    running_instances_ids.append(instance["_ID"])

            if state == "stopped":
                for instance in region[1][state]:
                    stopped_instances_ids.append(instance["_ID"])

        if service:
            instance_dict[region[0]] = managed_instances_ids
        else:
            if execute_action == "start":
                # instances_ids_list 
                pass
            if execute_action == "stop":
                instances_ids_list = managed_instances_ids + \
                                     running_instances_ids
                instance_dict[region[0]] = instances_ids_list
            if execute_action == "terminate":
                instances_ids_list  = managed_instances_ids + \
                                      running_instances_ids + \
                                      stopped_instances_ids
                instance_dict[region[0]] = instances_ids_list

    return instance_dict

def create_state_file(dictionary, state_file):
    state_file_dictionary = {}
    for region in dictionary.items():
        excluded_instance_list = []
        running_instance_list = []
        stopped_instance_list = []
        managed_instance_list = []
        region_inventory = {}

        for state in region[1]:
            if state == "exclude":
                for instance in region[1]['exclude']:
                    managed_instance_list.append(instance)
                    region_inventory["exclude"] = excluded_instance_list
            elif state == "running":
                for instance in region[1]['running']:
                    managed_instance_list.append(instance)
                    running_instance_list.append(instance)
                    region_inventory["managed"] = managed_instance_list
                    region_inventory["running"] = running_instance_list
            elif state == "stopped":
                for instance in region[1]['stopped']:
                    managed_instance_list.append(instance)
                    region_inventory["stopped"] = stopped_instance_list
        if len(region[1]) == 0:
            region_inventory["State"] = "Non Active"
        state_file_dictionary[region[0]] = region_inventory

    with open(state_file, 'w') as file:
        json.dump(state_file_dictionary, file, indent=4, sort_keys=True)

def confirm_state_file(file_path):
    try:
        state_file = read_json_file(file_path)
        schedule = state_file['_schedule']
        return True
    except ValueError:
        print ' State file corrupted. Create new by using --init\n '\
              ' sudo aws-ranger daemon --init '
        sys.exit()
    except KeyError:
        print "Missing schedule config. Run again with --init flag"
        sys.exit()
    except IOError:
        print "missing state file"
        sys.exit()

def read_json_file(json_file):
    return json.load(open(json_file))

def update_json_file(file_path, new_dictionary):
    orig_state_file = json.load(open(file_path))
    orig_state_file.update(new_dictionary)
    with open(file_path, 'w') as file:
        json.dump(orig_state_file, file, indent=4, sort_keys=True)

def update_dictionary(file_path, section, keys_and_values):
    state_file = json.load(open(file_path))
    state_file[section] = keys_and_values
    with open(file_path, 'w') as file:
        json.dump(state_file, file, indent=4, sort_keys=True)

class AWSRanger(object):
    def __init__(self, profile_name):
        try:
            self.aws_client(resource=False, 
                            profile_name=profile_name).describe_regions()
        except ClientError as e:
            print('Failed to Authenticate your AWS account\n'
            'Review your boto credentials file at ~/.aws/credentials')
            sys.exit()

    def aws_client(self, 
                   resource=True, 
                   profile_name='default',
                   region_name='eu-west-1', 
                   aws_service='ec2'):
        
        session = boto3.Session(profile_name=profile_name)

        if resource:
            return session.resource(aws_service, region_name=region_name)
        else:
            return session.client(aws_service, region_name=region_name)
        
    def get_all_regions(self):
        region_list = []
        response = self.aws_client(resource=False).describe_regions()['Regions']
        for region in response:
            region_api_id = region['Endpoint'].split('.')[1]
            region_list.append(region_api_id)
        return region_list

    def fetch_instances(self, region=False):
        return self.aws_client(region_name=region).instances.filter(Filters=[])

    def get_instances(self,
                      config_path, 
                      instances_state="running", 
                      region=False):
        all_instances = []
        region_list = []

        if region:
            region_list.append(region)
        else:
            for region in self.get_all_regions():
                try:
                    region_list.append(region)
                except ClientError:
                    print "Skipping region: {}".format(region)

        all_instances = {}

        for region in region_list:
            excluded_instance_list = []
            running_instance_list = []
            stopped_instance_list = []
            region_inventory = {}
            
            instances = self.fetch_instances(region)
            for instance in instances:
                instance_dict = {}
                instance_dict['_ID'] = instance.id
                instance_dict['State'] = instance.state['Name']
                instance_dict['Type'] = instance.instance_type
                instance_dict['Public DNS'] = instance.public_dns_name
                instance_dict['Creation Date'] = str(instance.launch_time)
                instance_dict['Tags'] = instance.tags
                try:
                    if instance.tags[0]['Value'].lower() in \
                    read_json_file_section(config_path, "EXCLUDE_TAGS"):
                        excluded_instance_list.append(instance_dict)
                        region_inventory['exclude'] = excluded_instance_list
                        continue
                except TypeError:
                    instance_dict['Tags'] = [{u'Value': 'none', u'Key': 'Tag'}]

                if instance.state['Name'] == 'stopped':
                    stopped_instance_list.append(instance_dict)
                    region_inventory['stopped'] = stopped_instance_list
                elif instance.state['Name'] == 'running':
                    running_instance_list.append(instance_dict)
                    region_inventory['running'] = running_instance_list
            all_instances[region] = region_inventory
        return all_instances

    def update_tags(self, instance_list, tags_list, region):
        for instance in instance_list:
            self.aws_client(region_name=region).create_tags(
                Resources=[instance], Tags=tags_list)

    def start_instnace(self, instance_list, region=False):
        for instance in instance_list:
            print('Starting instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=[instance]).start()

    def stop_instnace(self, instance_list, region=False):
        for instance in instance_list:
            print('Stopping instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=[instance]).stop()

    def terminate_instnace(self, instance_list, region=False):
        for instance in instance_list:
            print('Terminating instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=[instance]).terminate()
    
    def executioner(self,
                    config_path,
                    instances,
                    region=False,
                    action="pass"):
        
        tags_list = [{"Key":"aws-ranger Host", 
                      "Value":"{0} @ {1}".format(HOST_NAME, PUBLIC_IP)},
                      {"Key":"aws-ranger Last Action",
                      "Value":"{0} @ {1}".format(
                          action, Time.strftime("%Y-%m-%d %H:%M:%S"))},
                      {"Key":"aws-ranger User",
                      "Value":USER_NAME}]
        try:
            if action.lower() == 'stop':
                stop_dictionary = create_short_instances_dict(
                    instances, action.lower())
                for k, v in stop_dictionary.items():
                    self.stop_instnace(v, region=k)
                    self.update_tags(v, tags_list, region=k)
            elif action.lower() == 'start':
                start_dictionary = create_short_instances_dict(
                    instances, action.lower())
                for k, v in start_dictionary.items():
                    self.start_instnace(v, region=k)
                    self.update_tags(v, tags_list, region=k)
            elif action.lower() == 'terminate':
                terminate_dictionary = create_short_instances_dict(
                    instances, action.lower())
                for k, v in terminate_dictionary.items():
                    self.terminate_instnace(v, region=k)
            elif action == 'pass':
                pass
        except AttributeError:
            pass

class Scheduler(object):
    def __init__(self, config_path, state_file):
        self.config_file = config_path
        self.state_file = state_file

    def start_of_day(self, day):
        try:
            start_hour = str(read_json_file_section(
                self.config_file, "Working Hours")["Start of working Day"])
            if start_hour.endswith("PM"):
                start_hour = int(_return_digits(start_hour)) + 12
            else:
                start_hour = int(_return_digits(start_hour))
        except KeyError:
            start_hour = 9
        return  datetime.combine(day, time(start_hour, 00))

    def end_of_day(self, day):
        try:
            end_hour = str(read_json_file_section(
                self.config_file, "Working Hours")["End of working Day"])
            if end_hour.endswith("PM"):
                end_hour = int(_return_digits(end_hour)) + 12
            else:
                end_hour = int(_return_digits(end_hour))
        except KeyError:
            end_hour = 18
        return  datetime.combine(day, time(end_hour, 00))

    def next_weekday(self):
        workday = date.today() + timedelta(days=1)
        weekend = str(read_json_file_section(
            self.config_file, "Working Hours")["Last Day of the week"])
        
        thursday = ["Thursday", "Thu"]
        for day in thursday:
            if difflib.SequenceMatcher(None,a=weekend,b=day).ratio() > 0.9:
                # 4 is Friday and 5 is Saturday
                weekend = [4, 5]
            else:
                # 5 is Saturday and 6 is Sunday
                weekend = [5, 6]
            
        while workday.weekday() in weekend:
            workday = workday + timedelta(days=1)
        else:
            return workday

    def end_of_week(self):
        today = datetime.now()
        last_day = str(read_json_file_section(
            self.config_file, "Working Hours")["Last Day of the week"])
        
        thursday = ["Thursday", "Thu"]
        for day in thursday:
            if difflib.SequenceMatcher(None,a=last_day,b=day).ratio() > 0.9:
                # 3 for Thursday
                last_day = 3
            else:
                # 4 for Friday
                last_day = 4

        while today.weekday() != last_day:
            today = today + timedelta(days=1)
        end_of_week = self.end_of_day(today)
        return end_of_week
    
    def start_of_next_week(self):
        first_day = str(read_json_file_section(
            self.config_file, "Working Hours")["First Day of the Week"])
        sunday = ["Sunday", "Sun"]
        for day in sunday:
            if difflib.SequenceMatcher(None,a=first_day,b=day).ratio() > 0.9:
                # 6 for Sunday
                first_day = 6
            else:
                # 0 for Monday
                first_day = 0

        next_sunday = self.next_weekday()
        while next_sunday.weekday() != first_day:
            next_sunday = next_sunday + timedelta(days=1)
        start_of_week = self.start_of_day(next_sunday)
        return start_of_week

    def get_next_action(self, policy):
        now = datetime.now()
        take_five = now + timedelta(minutes=5)
        if policy == 'full':
            if now < self.start_of_day(now):
                return ['start', self.start_of_day(now)]
            elif now > self.end_of_day(now):
                return ['start', self.start_of_day(self.next_weekday())]
            elif now < self.end_of_day(now):
                return ['stop', self.end_of_day(now)]
        elif policy == 'nightly':
            if now > self.end_of_day(now):
                return ['stop', take_five]
            elif now < self.start_of_day(now):
                return ['stop', take_five]
            else:
                return ['stop', self.end_of_day(now)]
        elif policy == 'workweek':
            if self.end_of_day(now) < now < self.start_of_day(
                                                self.next_weekday()):
                return ['stop', take_five]
            elif now < self.end_of_week():
                return ['stop', self.end_of_week()]

    def set_schedule_section(self, policy, state_file):
        next_task = self.get_next_action(policy)
        schedule_info = {'policy': policy, 
                        'Next Task': next_task[0],
                        'Time': next_task[1].strftime("%Y-%m-%d %H:%M:%S")}
        update_dictionary(state_file, '_schedule', schedule_info)
        return schedule_info
    
    def compare_times(self, target_time):
        target_convert = datetime.strptime(target_time, '%Y-%m-%d %H:%M:%S')
        if target_convert > datetime.now():
            return True

    def cron_run(self, 
                 config_path, 
                 state_file, 
                 region, 
                 policy, 
                 execute, 
                 instances):
        
        if _find_duplicate_processes("aws-ranger"):
            sys.exit()

        schedule_info = self.set_schedule_section(policy, state_file)

        # Once cron is configured, This section will execute each run
        ranger = AWSRanger(profile_name="default")
        instances = ranger.get_instances(config_path, region=region)
        update_dictionary(state_file, '_schedule', schedule_info)
        update_json_file(state_file, instances)
        next_run = read_json_file_section(state_file, "_schedule")
        if self.compare_times(next_run["Time"]):
            ranger.executioner(config_path, 
                               instances, 
                               action=next_run["Next Task"])
        else:
            pass


CLICK_CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    token_normalize_func=lambda param: param.lower(),
    ignore_unknown_options=True)

@click.group(invoke_without_command=True, 
             context_settings=CLICK_CONTEXT_SETTINGS)
@click.pass_context
@click.option('--init',
              is_flag=True,
              help="Config aws-ranger for first use")
@click.option('-r',
              '--region',
              default="eu-west-1",
              help=' Specify the region\n'\
                   ' Default to "eu-west-1"')
@click.option('-x',
              '--execute',
              help=' What action to carry out on instances not protected?   \b'
                   ' Stop, Start or Terminate ')
def ranger(ctx, init, region, execute):
    """Round up your AWS instances

    Scout for Instances in all AWS Regions
    """

    if not _internet_on():
        print "No Internet connection"
        sys.exit()
    
    DEFAULT_AWS_PROFILE = find_profiles(BOTO_CREDENTIALS)[0]
    CONFIG_PATH = '{0}/{1}.conf'.format(AWS_RANGER_HOME,
                                        DEFAULT_AWS_PROFILE)
    STATE_FILE = '{0}/{1}.state'.format(AWS_RANGER_HOME,
                                        DEFAULT_AWS_PROFILE)

    if init:
        if os.path.exists(AWS_RANGER_HOME):
            print "aws-ranger Home exists, checking config..."
            if os.path.exists(CONFIG_PATH):
                print "Hi"
                if _yes_or_no(' aws-ranger was already initiated, '\
                              ' Overwrite config? '):
                    _safe_remove(CONFIG_PATH)
                    create_config_file(CONFIG_PATH, DEFAULT_AWS_PROFILE)
            else:
                print "Creating aws-ranger config file"
                create_config_file(CONFIG_PATH, DEFAULT_AWS_PROFILE)
        else:
            if _yes_or_no(' You are about to create Home dir for aws-ranger.\n '
                          ' Continue? '):
                os.makedirs(AWS_RANGER_HOME)
                create_config_file(CONFIG_PATH, DEFAULT_AWS_PROFILE)
    
    validate_ranger(AWS_RANGER_HOME, CONFIG_PATH)
    
    ranger = AWSRanger(profile_name='default')

    if region == "all":
        region = None

    instances = ranger.get_instances(CONFIG_PATH, region=region)
    
    ranger.executioner(CONFIG_PATH, instances, action=execute)
    
    if ctx.invoked_subcommand is None and not execute:
        print _format_json(instances)
        sys.exit()

    ctx.obj = [CONFIG_PATH, STATE_FILE, instances, region]

@ranger.command('cron')
@click.pass_obj
@click.option('--init',
              is_flag=True,
              help='Sets cron, insert _schedule key to state_file '
                   'Configures schedule section and policy')
@click.option('-p',
              '--policy',
              default="nightly",
              help=' Which policy to enforce?\n '\
                   ' Nightly, Workweek or Full ')
@click.option('-x',
              '--execute',
              default="stop",
              help=' Which action to execute on managed instances?      \b '
                   ' Stop or Terminate ')
@click.option('-s',
              '--stop',
              is_flag=True,
              help='Remove aws-ranger from cron')
def cron(ctx, policy, execute, init, stop):
    """Run aws-ranger as a cron job.\n
    
    \b 
    Control aws-ranger by setting the policy,
    [nightly]: Executes (stop\ terminate) on Instances every end of day
    [workweek]: Executes (stop\ terminate) on Instances just before the weekend
    [full]: Executes (stop\ start) on Instances Daily and over the weekend

    Set the Execution that aws-ranger will enforce [stop, terminate, alert]\n
    You can limit aws-ranger control to one region.\n
    """
    CONFIG_PATH = ctx[0]
    STATE_FILE = ctx[1]
    instances = ctx[2]
    region = ctx[3]

    args = '-r {0} {1} -p {2} -x {3}'.format(region, "cron", policy, execute)
    
    if stop:
        _kill_process("aws-ranger")
        _config_cronjob("unset", comment="aws-ranger")
        _safe_remove(STATE_FILE)
        sys.exit()
    
    if _find_duplicate_processes("aws-ranger"):
        print "aws-ranger already running! quiting..."
        sys.exit()

    if policy not in ['nightly', 'workweek', 'full']:
        print "Policy not Found! Review and select one of three"
        sys.exit()
    
    validate_ranger(AWS_RANGER_HOME, CONFIG_PATH)
    
    if init:
        if os.path.isfile(STATE_FILE):
            if _yes_or_no("State file exists, Do you want to overwrite it?"):
                instances = create_state_file(instances, STATE_FILE)
                scheduler = Scheduler(config_path=CONFIG_PATH, 
                                      state_file=STATE_FILE)
                update_dictionary(STATE_FILE, '_schedule', "init")
                scheduler.set_schedule_section(policy, STATE_FILE)
                _config_cronjob("set",
                                command=CURRENT_FILE,
                                args=args,
                                comment="aws-ranger")
            else:
                print "Aborting! you must add schedule section into state file"
                sys.exit()
        else:
            print "Creating aws-ranger state file"
            instances = create_state_file(instances, STATE_FILE)
            scheduler = Scheduler(config_path=CONFIG_PATH, 
                                  state_file=STATE_FILE)

            scheduler.set_schedule_section(policy, STATE_FILE)
            _config_cronjob("set",
                            command=CURRENT_FILE,
                            args=args,
                            comment="aws-ranger")
    
    if os.path.isfile(STATE_FILE) and confirm_state_file(STATE_FILE):
        scheduler = Scheduler(config_path=CONFIG_PATH, state_file=STATE_FILE)

        scheduler.start_of_day(scheduler.next_weekday())
        scheduler.cron_run(CONFIG_PATH,
                           STATE_FILE,
                           region,
                           policy,
                           execute,
                           instances)
    else:
        print "State file missing or corrupted. run `aws-ranger cron --init`"
        sys.exit()
