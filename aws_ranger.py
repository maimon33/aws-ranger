import re
import os
import sys
import json
import sched
import urllib2
import smtplib

from datetime import time, date, timedelta, datetime

import serv
import boto3
import click

# from wryte import Wryte
from botocore.exceptions import ClientError

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
    AWS_RANGER_CONFIG = {}
    TAGS_DICTIONARY = {}
    TIMES_DICTIONARY = {}
    EMAIL_DICTIONARY = {}
    if os.path.isfile(config_path):
        if _yes_or_no("Config file exist, Do you wish to proceed?"):
            print('\nCreating config file...')
            
            # Tags section
            DEFAULT_EXCLUDE_TAGS = ["prod", "production", "free range"]
            TEXT = """\nPlease enter tag values to exclude them 
from the aws-ranger (please use comma to separate them)
prod, production, free range:"""
            EXCLUDE_TAGS = raw_input(TEXT).split(",")
            if len(EXCLUDE_TAGS) == 1:
                EXCLUDE_TAGS = DEFAULT_EXCLUDE_TAGS
            AWS_RANGER_CONFIG["EXCLUDE_TAGS"] = EXCLUDE_TAGS
            
            # Time definition section
            # TIMES_DICTIONARY["START_OF_DAY"] = "datetime.combine(date.today(), time(9, 00))"
            TIMES_DICTIONARY["START_OF_DAY_TOMORROW"] = "datetime.combine((date.today()+ timedelta(days=1)), time(9, 00))"
            TIMES_DICTIONARY["END_OF_DAY"] = "datetime.combine(date.today(), time(18, 00))"
            TIMES_DICTIONARY["START_OF_WEEK"] = "dt - timedelta(days=dt.weekday()-1)"
            TIMES_DICTIONARY["LAST_DAY_OF_WEEK"] = "{} + timedelta(days=4)"
            AWS_RANGER_CONFIG["TIMES"] = TIMES_DICTIONARY

            # Email section
            EMAIL_DICTIONARY['GMAIL_ACCOUNT'] = raw_input("Gmail account? ")
            EMAIL_DICTIONARY['GMAIL_PASSWORD'] = raw_input("Gmail password? ")
            EMAIL_DICTIONARY['DESTINATION_EMAIL'] = raw_input(
                "Notification Destination? ")
            AWS_RANGER_CONFIG["EMAIL"] = EMAIL_DICTIONARY
            with open(config_path, 'w') as file:
                json.dump(AWS_RANGER_CONFIG, file, indent=4)

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

class aws_ranger():
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

    def get_instances(self, instances_state="running", region=False):
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
                        region_inventory["stopped"] = managed_instance_list
            if len(region[1]) == 0:
                region_inventory["State"] = "Non Active"
            state_file_dictionary[region[0]] = region_inventory
        # return state_file_dictionary

        with open(state_file, 'w') as file:
            json.dump(state_file_dictionary, file, indent=4, sort_keys=True)

    def start_instnace(self, instance_list, region=False):
        for instance in instance_list:
            print('Starting instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=instance).start()

    def stop_instnace(self, instance_list, region=False):
        for instance in instance_list:
            print('Stopping instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=instance).stop()

    def terminate_instnace(self, instance_list, region=False):
        for instance in instance_list:
            print('Terminating instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=instance_list).terminate()

class scheduler():
    # current = date.today().strftime('%d/%m/%y %H:%M')
    # dt = datetime.strptime(current, "%d/%m/%y %H:%M")

    def next_weekday(self, d, weekday):
        days_ahead = weekday - d.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return d +timedelta(days_ahead)

    def end_of_day(self):
        target = datetime.combine(date.today(), time(18, 00))
        seconds = (target - datetime.now()).seconds
        return seconds
    
    def tomorrow_morning(self):
        target = datetime.combine((date.today() + timedelta(days=1)),
                                  time(9, 00))
        seconds = (target - datetime.now()).seconds
        return seconds

    def end_of_week(self):
        d = datetime.date(datetime.now())
        next_thursday = self.next_weekday(d, 3) # 3 for next Thursday
        end_of_week = datetime.combine(next_thursday, time(18, 00))
        return end_of_week
    
    def next_sunday(self):
        d = datetime.date(datetime.now())
        next_sunday = self.next_weekday(d, 6) # 6 for next Sunday
        start_of_week = datetime.combine(next_sunday, time(9, 00))
        return next_sunday

    def get_seconds_difference(self, policy):
        now = datetime.now()
        target = self.end_of_week()
        seconds = (target - now).seconds
        return seconds

    def set_policy(self):
        print self.get_seconds_difference("policy")
        # print policy
    
    def get_scheduled_event_command(self, action, target_datetime):
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
@click.option('-v',
              '--verbose',
              is_flag=True,
              help="display run log in verbose mode")
@click.option('-d',
              '--debug',
              is_flag=True,
              help="debug new features")
def ranger(ctx, init, verbose, debug):
    """Round up your AWS instances

    Scout for Instances in all AWS Regions
    """
    # if verbose:
        # wryter = Wryte(name='wryte', level='debug')
        
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
    
    ranger = aws_ranger(profile_name='default')
    
    if debug:
        # create_config_file(CONFIG_PATH)
        # send_mail(CONFIG_PATH, "Message from the ranger", "Hi, Found this!")
        timer = scheduler()
        timer.set_policy()
        # print timer.get_seconds_difference(CONFIG_PATH)
        
        sys.exit()
    
    if ctx.invoked_subcommand is None:
        instances = create_short_instances_dict(ranger.get_instances())
        print instances

@ranger.command('stop')
@click.pass_obj
@click.argument('region', default=False)
def stop(ctx, region):
    """Stop instances Found by aws-ranger
    """
    CONFIG_PATH = ctx[0]
    ranger = aws_ranger(profile_name='default')

    instances = ranger.get_instances()
    stop_list = create_short_instances_dict(instances)
    for k, v in stop_list.items():
        ranger.stop_instnace(v, region=k)

@ranger.command('start')
@click.pass_obj
@click.argument('region', default=False)
def start(ctx, region):
    """Start managed instances Found by aws-ranger
    """
    CONFIG_PATH = ctx[0]
    ranger = aws_ranger(profile_name='default')

    instances = ranger.get_instances()
    start_list = create_short_instances_dict(instances)
    for k, v in start_list.items():
        ranger.start_instnace(v, region=k)

@ranger.command('terminate')
@click.pass_obj
@click.argument('region', default=False)
def terminate(region):
    """Terminate instances Found by aws-ranger
    """
    ranger = aws_ranger(profile_name='default')

    instances = ranger.get_instances()
    stop_list = create_short_instances_dict(instances)
    for k, v in stop_list.items():
        ranger.terminate_instnace(v, region=k)

    instances = ranger.get_instances(instances_state="stopped")
    stop_list = create_short_instances_dict(instances)
    for k, v in stop_list.items():
        ranger.terminate_instnace(v, region=k)

@ranger.command('deamon')
@click.pass_obj
@click.argument('policy', default="nightly")
@click.argument('region', default=False)
@click.argument('action', default="stop")
def deamon(policy, region, action):
    """Run aws-ranger as a deamon.\n
    
    \b 
    Control aws-ranger by setting the policy,
    [nightly]: Actions on Instances every end of day
    [work week]: Actions on Instances as soon as the weekend starts

    Set the action aws-ranger will enforce [stop, terminate, alert]\n
    You can limit aws-ranger control to one region.\n
    """
    CONFIG_PATH = ctx[0]
    STATE_FILE = ctx[1]

    print policy

    # Checks you are running with sudo privileges
    if os.getuid() != 0:
        print('You run with sudo privileges to run a deamon')
        sys.exit()

    ranger = aws_ranger(profile_name='default')
    ranger.create_state_file(ranger.get_instances(), STATE_FILE)
    managed_instances = create_short_instances_dict(ranger.get_instances(), 
                                                    service=True)

    if alert:
        send_mail("Subject", "Mail content")
    pass