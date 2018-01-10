import re
import os
import sys
import json
import sched


from datetime import time, date, timedelta, datetime

# import serv
import boto3
import click

from wryte import Wryte
from botocore.exceptions import ClientError

USER_HOME = os.getenv("HOME")
AWS_RANGER_HOME = '{0}/.aws-ranger'.format(USER_HOME)
BOTO_CREDENTIALS = '{0}/.aws/credentials'.format(USER_HOME)
TAGS_EXCLUDE_KEY_WORDS = ["prod", "Production", "do not stop"]

# def _config():
#     wryter.info('Please provide AWS Credentials')
#     AWS_ACCESS_KEY_ID=raw_input('Enter Your AWS Access Key ID : ')
#     AWS_SECRET_ACCESS_KEY=raw_input('Enter Your AWS Secret Access Key : ')
#     AWS_ACCOUNT_ALIAS=raw_input('Enter an Alias for the Account: ')
    
#     config = {"aws-account": {'AWS_ACCOUNT_ALIAS': AWS_ACCOUNT_ALIAS,
#                               'AWS_ACCESS_KEY_ID': AWS_ACCESS_KEY_ID, 
#                               'AWS_SECRET_ACCESS_KEY': AWS_SECRET_ACCESS_KEY}}
#     with open('{0}/{1}.json'.format(CONF_DIR, AWS_ACCOUNT_ALIAS), 'w') as file:
#         json.dump(config, file, indent=4)

# try:
#     if os.listdir(CONF_DIR) == []:
#         raise NameError
#     for file in os.listdir(CONF_DIR):
#         if file.endswith(".json"):
#             global CONFIG_PATH
#             CONFIG_PATH = '{}/{}'.format(CONF_DIR, file)
#         with open(CONFIG_PATH) as config_file:
#             cfg = json.load(config_file)["aws-account"]
# except NameError:
#     wryter.info('Needs to be configured first')
    # _config()
    # with open(CONFIG_PATH) as config_file:
    #     cfg = json.load(config_file)["aws-account"]


def _format_json(dictionary):
    return json.dumps(dictionary, indent=4, sort_keys=True)

def _yes_or_no(question):
    while True:
        reply = str(raw_input(question+' (y/n): ')).lower().strip()
        if reply[0] == 'y':
            return True
        else:
            wryter.info('Wrong answer. Bye')

def create_config_file(config_path, profile_name="default"):
    TEXT = """Please enter tag values to exclude
        them from the aws-ranger (please comma to seperate them)
        [prod, production, do not stop, keep]:"""
    EXCLUDE_TAGS = raw_input(TEXT) or ["prod", "production", "do not stop", "keep"]
    print EXCLUDE_TAGS
    with open(config_path, 'w') as file:
        EXCLUDE_TAGS = raw_input("Please enter tag values to exclude\
        them from the aws-ranger (please comma to seperate them)\
        [prod, production, do not stop, keep]:") or ["prod", "production", "do not stop", "keep"]
        print EXCLUDE_TAGS
    pass

def find_profiles(file):
    profiles_list = []
    boto_config = open(file).read()
    for match in re.findall("\[.*\]", boto_config):
        profiles_list.append(match.strip("[]"))
    return profiles_list
        
def create_short_instances_dict(all_instances_dictionary):
    instance_dict ={}

    for region in all_instances_dictionary.items():
        instances_ids_list = []
        try:
            region[1]["running"]
            region[1]["stopped"]
            region[1]["exclude"]
        except KeyError:
            region[1]["Region State"] = "Region vacent"
        
        for state in region[1]:
            if state in {"running", "stopped"}:
                for instance in region[1][state]:
                    instances_ids_list.append(instance["ID"])
                    instance_dict[region[0]] = instances_ids_list
    return instance_dict

class aws_ranger():
    def __init__(self, profile_name):
        wryter = Wryte(name='aws-ranger')
        try:
            self.aws_client(resource=False, 
                            profile_name=profile_name).describe_regions()
        except ClientError as e:
            wryter.info('Failed to Authenticate your AWS account\n'
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
        state_file_dictionary = {}

        for region in region_list:
            excluded_instance_list = []
            running_instance_list = []
            stopped_instance_list = []
            region_inventory = {}
            instances = self.fetch_instances(region)
            for instance in instances:
                instance_dict = {}
                instance_dict['ID'] = instance.id
                instance_dict['State'] = instance.state['Name']
                instance_dict['Type'] = instance.instance_type
                instance_dict['Public DNS'] = instance.public_dns_name
                instance_dict['Creation Date'] = str(instance.launch_time)
                instance_dict['Tags'] = instance.tags
                try:
                    if instance.tags[0]['Value'].lower() in TAGS_EXCLUDE_KEY_WORDS:
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
    
    def create_state_file(self, dictionary):
        with open(STATE_FILE, 'w') as file:
            file.truncate()
            json.dump(dictionary, file, indent=4)
        pass

    def start_instnace(self, instance_list, region=False):
        for instance in instance_list:
            wryter.info('Starting instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=instance).start()

    def stop_instnace(self, instance_list, region=False):
        for instance in instance_list:
            wryter.info('Stopping instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=instance).stop()

    def terminate_instnace(self, instance_list, region=False):
        for instance in instance_list:
            wryter.info('Terminating instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=instance_list).terminate()

class scheduler():
    current = date.today().strftime('%d/%m/%y %H:%M')
    dt = datetime.strptime(current, "%d/%m/%y %H:%M")
    START_OF_DAY = datetime.combine(date.today(),
                                    time(9, 00))
    END_OF_DAY = datetime.combine(date.today(), 
                                  time(18, 00))
    START_OF_WEEK = dt - timedelta(days=dt.weekday()-1)
    LAST_DAY_OF_WEEK = START_OF_WEEK + timedelta(days=4)

    def get_seconds_difference(self, target_datetime):
        now = datetime.now()
        seconds = (target_datetime - now).seconds
        return seconds

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
    if verbose:
        wryter = Wryte(name='wryte', level='debug')
        
    DEFAULT_AWS_PROFILE = find_profiles(BOTO_CREDENTIALS)[0]
    CONFIG_PATH = '{0}/{1}.conf'.format(AWS_RANGER_HOME,
                                        DEFAULT_AWS_PROFILE)
    STATE_FILE = '{0}/{1}.state'.format(AWS_RANGER_HOME,
                                        DEFAULT_AWS_PROFILE)
    ctx.obj = [CONFIG_PATH, STATE_FILE]
    
    wryter = Wryte(name='aws-ranger')

    if init:
        confirm = 'You are about to create Home dir for aws-ranger.\n'
        'Continue?'
        if os.path.exists(AWS_RANGER_HOME):
            wryter.info('aws-ranger was already initiated')
            sys.exit()

        if _yes_or_no(confirm):
            os.makedirs(AWS_RANGER_HOME)
            create_config_file(CONFIG_PATH, DEFAULT_AWS_PROFILE)
            sys.exit()
        else:
            sys.exit()
    
    if not os.path.exists(AWS_RANGER_HOME):
        wryter.info('Missing aws-ranger HOME dir\n'
        'Run `aws-ranger --config` or create it yourself at ~/.aws-ranger')
        sys.exit()
    
    ranger = aws_ranger(profile_name='default')
    
    if debug:
        create_config_file(CONFIG_PATH, DEFAULT_AWS_PROFILE)
        # ranger.create_state_file(ranger.get_instances())
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
@click.argument('region', default=False)
@click.option('-a',
              '--alert',
              is_flag=True,
              help='No Action, Just alert by mail')
def deamon(region):
    wryter = Wryte(name='aws-ranger')

    # Checks you are running with sudo privileges
    if os.getuid() != 0:
        wryter.info('You run with sudo privileges to run a deamon')
        sys.exit()

    ranger = aws_ranger(profile_name='default')
    pass