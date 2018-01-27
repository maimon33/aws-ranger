import re
import os
import sys
import json
import time as T
# import sched

import urllib2
import smtplib

from crontab import CronTab
from datetime import time, date, timedelta, datetime
# from threading import Timer

import serv
import boto3
import click

# from wryte import Wryte
from daemon import DaemonContext
from botocore.exceptions import ClientError
from apscheduler.schedulers.background import BackgroundScheduler

USER_HOME = os.getenv("HOME")
AWS_RANGER_HOME = '{0}/.aws-ranger'.format(USER_HOME)
BOTO_CREDENTIALS = '{0}/.aws/credentials'.format(USER_HOME)

def _format_json(dictionary):
    return json.dumps(dictionary, indent=4, sort_keys=True)

def internet_on():
    try:
        urllib2.urlopen('http://www.google.com', timeout=1)
        return True
    except urllib2.URLError as err: 
        return False

def _yes_or_no(question):
    while True:
        reply = str(raw_input(question+' (y/n): ')).lower().strip()
        if reply[0] == 'y':
            return True
        else:
            print 'You replied No. Bye'
            return False

def create_config_file(config_path, profile_name="default"):
    # wryter = Wryte(name='aws-ranger')
    aws_ranger_config = {}
    email_dictionary = {}
    if os.path.isfile(config_path):
        if _yes_or_no("Config file exist, Do you wish to proceed?"):
            print('\nCreating config file...')
            
            # Tags section
            default_exclude_tags = ["prod", "production", "free range"]
            text = """\nPlease enter tag values to exclude them 
from the aws-ranger (please use comma to separate them)
prod, production, free range:"""
            exclude_tags = raw_input(text).split(",")
            if len(exclude_tags) == 1:
                exclude_tags = default_exclude_tags
            aws_ranger_config["EXCLUDE_TAGS"] = exclude_tags

            # Email section
            email_dictionary['GMAIL_ACCOUNT'] = raw_input("Gmail account? ")
            email_dictionary['GMAIL_PASSWORD'] = raw_input("Gmail password? ")
            email_dictionary['DESTINATION_EMAIL'] = raw_input(
                "Notification Destination? ")
            aws_ranger_config["EMAIL"] = email_dictionary
            with open(config_path, 'w') as file:
                json.dump(aws_ranger_config, file, indent=4)

        else:
            print('Config file found. Try to run aws-ranger without --config')
            sys.exit()

def read_config_file(config_path, requested_data, profile_name="default"):
    ranger_config = json.load(open(config_path))
    return ranger_config[requested_data]

def send_mail(config_path, subject, msg):
    email_config = read_config_file(config_path, "EMAIL")
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
        
def create_short_instances_dict(all_instances_dictionary, service=False):
    instance_dict ={}

    for region in all_instances_dictionary.items():
        instances_ids_list = []
        try:
            region[1]["running"]
            region[1]["stopped"]
            region[1]["exclude"]
            region[1]["managed"]
        except KeyError:
            region[1]["Region State"] = "Region vacent"
        
        if service:
            for state in region[1]:
                if state in {"managed"}:
                    for instance in region[1][state]:
                        instances_ids_list.append(instance["_ID"])
                        instance_dict[region[0]] = instances_ids_list
        else:
            for state in region[1]:
                if state in {"running", "stopped"}:
                    for instance in region[1][state]:
                        instances_ids_list.append(instance["_ID"])
                        instance_dict[region[0]] = instances_ids_list
    return instance_dict

def read_state_file(state_file):
    return json.load(open(state_file))

def set_schedule_section(policy, state_file):
    # TODO: Take policy arg and update Next Task and Time
    #       Use function to return dict with both items
    state_file = json.load(open(state_file))
    schedule['_schedule'] = {'Policy': policy,
                            'Next Task': 'Stop',
                            'Time': '9PM'}
    with open(state_file, 'w') as file:
        json.dump(schedule, file, indent=4, sort_keys=True)

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
        
    def _get_all_regions(self):
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
            for region in self._get_all_regions():
                region_list.append(region)

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
                    read_config_file(config_path, "EXCLUDE_TAGS"):
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
    
    def create_state_file(self, dictionary, state_file):
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

class Scheduler(object):
    def __init__(self, object):
        pass

    def start_of_day(self, day):
        return  datetime.combine(day, time(9, 00))

    def end_of_day(self, day):
        return  datetime.combine(day, time(18, 00))

    def next_weekday(self):
        workday = date.today() + timedelta(days=1)
        while workday.weekday() in [4, 5]:
            # 4 is Friday and 5 is Saturday
            workday = workday + timedelta(days=1)
        else:
            return workday

    def end_of_week(self):
        next_thursday = self.next_weekday()
        while next_thursday.weekday() != 3: # 3 for next Thursday
            next_thursday = next_thursday + timedelta(days=1)
        end_of_week = self.end_of_day(next_thursday)
        return end_of_week
    
    def start_of_next_week(self):
        next_sunday = self.next_weekday()
        while next_sunday.weekday() != 6: # 3 for next Sunday
            next_sunday = next_sunday + timedelta(days=1)
        start_of_week = self.start_of_day(next_sunday)
        return start_of_week

    def get_next_action(self, policy):
        today = datetime.now()
        if policy == 'full':
            if today < self.end_of_day(today):
                return ['stop', self.end_of_day(today)]
            if today > self.end_of_day(today):
                return ['start', self.start_of_day(self.next_weekday)]
        elif policy == 'nightly':
            if today < self.end_of_day(today):
                return ['stop', self.end_of_day(today)]
        elif policy == 'workweek':
            if today < self.end_of_week(today):
                return ['stop', self.end_of_week(end_of_week())]
    
    def get_seconds_difference(self, target):
        now = datetime.now()
        seconds = (target - now).seconds
        return seconds
    
    def print_event(self):
        print 'EVENT:', T.time(), "Hi"
        return 'EVENT:', T.time(), "Hi"
    
    def get_schedule(self, policy):
        # print dir(apscheduler)
        # sched = BackgroundScheduler(trigger='cron')
        sched = BackgroundScheduler(trigger='date')
        sched.start()
        print sched.print_jobs()
        # print sched.add_job()
        print T.time()
        trigger = OrTrigger([CronTrigger(hour=1, minute=30)])
        job = sched.add_job(self.print_event, trigger)
        # job = sched.add_job(self.print_event, 2)
        T.sleep(60)
        print T.time()
        print sched.print_jobs()
        # s = sched.scheduler(T.time, T.sleep)
        # if len(s.queue) > 1:
        #     print "Found item!"
        # else:
        #     s.enter(5, 1, self.print_event, ())
        # print len(s.queue)
        # print s.queue
        # s.run()
        # T.sleep(5)
        # print s.queue
        # print T.time()
        # Timer(30, self.print_event, ()).start()
        # print dir(Timer)
        # T.sleep(15)
        # print T.time()

    def set_next_action(self, action, time):
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
@click.option('-x',
              '--execute',
              help="""
What action to carry out on instances found?         
you can Stop, Start or Terminate""")
@click.argument('region', default=False)
def ranger(ctx, init, execute, region):
    """Round up your AWS instances

    Scout for Instances in all AWS Regions
    """

    if not internet_on():
        print "No Internet connection"
        sys.exit()
    
    DEFAULT_AWS_PROFILE = find_profiles(BOTO_CREDENTIALS)[0]
    CONFIG_PATH = '{0}/{1}.conf'.format(AWS_RANGER_HOME,
                                        DEFAULT_AWS_PROFILE)
    STATE_FILE = '{0}/{1}.state'.format(AWS_RANGER_HOME,
                                        DEFAULT_AWS_PROFILE)
    
    ctx.obj = [CONFIG_PATH, STATE_FILE]

    if init:
        confirm = 'You are about to create Home dir for aws-ranger.\n'
        'Continue?'
        if os.path.exists(AWS_RANGER_HOME):
            print('aws-ranger was already initiated')
            sys.exit()

        if _yes_or_no(confirm):
            os.makedirs(AWS_RANGER_HOME)
            create_config_file(CONFIG_PATH, DEFAULT_AWS_PROFILE)
            sys.exit()
        else:
            sys.exit()
    
    if not os.path.exists(AWS_RANGER_HOME):
        print('Missing aws-ranger HOME dir\n'
        'Run `aws-ranger --config` or create it yourself at ~/.aws-ranger')
        sys.exit()
    
    ranger = AWSRanger(profile_name='default')

    instances = ranger.get_instances(CONFIG_PATH)
    
    try:
       if execute.lower():
            if execute.lower() == 'stop':
                stop_list = create_short_instances_dict(instances)
                for k, v in stop_list.items():
                    ranger.stop_instnace(v, region=k)
            elif execute.lower() == 'start':
                start_list = create_short_instances_dict(instances)
                for k, v in start_list.items():
                    ranger.start_instnace(v, region=k)
            elif execute.lower() == 'terminate':
                terminate_list = create_short_instances_dict(instances)
                stopped_list = create_short_instances_dict(
                    ranger.get_instances(CONFIG_PATH, 
                                         instances_state="stopped"))
                for k, v in terminate_list.items():
                    ranger.terminate_instnace(v, region=k)
                for k, v in stopped_list.items():
                    ranger.terminate_instnace(v, region=k)
    except AttributeError:
        print "Did not receive action to execute. printing current state"

    if ctx.invoked_subcommand is None and execute is None:
        print _format_json(instances)
        sys.exit()

@ranger.command('daemon')
@click.pass_obj
@click.argument('policy', default="nightly")
@click.argument('action', default="stop")
@click.argument('region', default=False)
@click.option('--init',
              is_flag=True,
              help="""
Sets daemon, insert _schedule key to state_file             
Configures schedule section and policy""")
def daemon(ctx, policy, action, region, init):
    """Run aws-ranger as a daemon.\n
    
    \b 
    Control aws-ranger by setting the policy,
    [nightly]: Actions (stop\ terminate) on Instances every end of day
    [workweek]: Actions (stop\ terminate) on Instances just before the weekend
    [full]: Actions (stop\ start) on Instances Daily and over the weekend

    Set the Action that aws-ranger will enforce [stop, terminate, alert]\n
    You can limit aws-ranger control to one region.\n
    """
    CONFIG_PATH = ctx[0]
    STATE_FILE = ctx[1]

    if policy not in ['nightly', 'workweek', 'full']:
        print "Policy not Found! Review and select one of three"
        sys.exit()

    # Checks you are running with sudo privileges
    # if os.getuid() != 0:
    #     print('You run with sudo privileges to run a deamon')
    #     sys.exit()

    ranger = AWSRanger(profile_name='default')
    scheduler = Scheduler('object')
    
    if os.path.isfile(STATE_FILE):
        if init:
            if _yes_or_no("State file exists, Do you want to overwrite it?"):
                instances = ranger.create_state_file(
                    ranger.get_instances(CONFIG_PATH), STATE_FILE)
                set_schedule_section(policy, STATE_FILE)
            else:
                print "Aborting! you must add schedule section into state file"
                sys.exit()
        else:
            state_file = read_state_file(STATE_FILE)
            
            try:
                schedule = state_file['_schedule']
            # TODO: Found state file. starting daemon and keeping doing the good work
            # Check if schedule section is found. else print missing and run with init
            except KeyError:
                print "Missing schedule config. Run again with --init flag"
                sys.exit()
            
            scheduler.get_next_action(policy)
            
    else:
        instances = read_state_file(STATE_FILE)
    

    # TODO: start logic only after everyting is ready
    # if not instances:
    #     print "No Instances found!"
    #     scheduler._daemonize(scheduler.service_action(policy), policy)
    # else:
    #     managed_list = create_short_instances_dict(instances, service=True)
    

    # if action == "stop":
    #     for k, v in managed_list.items():
    #         ranger.stop_instnace(v, region=k)
    # elif action == "terminate":
    #     for k, v in managed_list.items():
    #         ranger.terminate_instnace(v, region=k)
    # elif action == "alert":
    #     send_mail("Subject", "Mail content")
    # else:
    #     print "Can't find action"
