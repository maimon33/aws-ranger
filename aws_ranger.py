import os
import sys
import json
import sched
import logging

from datetime import time, date, timedelta, datetime

import serv
import boto3
import click

from botocore.exceptions import ClientError

# Setting up a logger
logger = logging.getLogger('AWS ranger')
logger.setLevel(logging.INFO)
console = logging.StreamHandler()
logger.addHandler(console)

HOME_DIR = '{0}/.aws-ranger'.format(os.getenv("HOME"))
CONF_DIR = '{0}/aws-creds'.format(HOME_DIR)

def _config():
    logger.info('Please provide AWS Credentials')
    AWS_ACCESS_KEY_ID=raw_input('Enter Your AWS Access Key ID : ')
    AWS_SECRET_ACCESS_KEY=raw_input('Enter Your AWS Secret Access Key : ')
    AWS_ACCOUNT_ALIAS=raw_input('Enter an Alias for the Account: ')
    
    config = {"aws-account": {'AWS_ACCOUNT_ALIAS': AWS_ACCOUNT_ALIAS,
                              'AWS_ACCESS_KEY_ID': AWS_ACCESS_KEY_ID, 
                              'AWS_SECRET_ACCESS_KEY': AWS_SECRET_ACCESS_KEY}}
    with open('{0}/{1}.json'.format(CONF_DIR, AWS_ACCOUNT_ALIAS), 'w') as file:
        json.dump(config, file, indent=4)
    
    global CONFIG_PATH
    CONFIG_PATH = '{0}/{1}.json'.format(CONF_DIR, AWS_ACCOUNT_ALIAS)

try:
    if not os.path.exists(CONF_DIR):
        os.makedirs(CONF_DIR)
except OSError:
    logger.warning('Error Creating config folder')

try:
    if os.listdir(CONF_DIR) == []:
        raise NameError
    for file in os.listdir(CONF_DIR):
        if file.endswith(".json"):
            global CONFIG_PATH
            CONFIG_PATH = '{}/{}'.format(CONF_DIR, file)
        with open(CONFIG_PATH) as config_file:
            cfg = json.load(config_file)["aws-account"]
except NameError:
    logger.info('Needs to be configured first')
    _config()
    with open(CONFIG_PATH) as config_file:
        cfg = json.load(config_file)["aws-account"]

CONFIG_PATH = '{0}/{1}.json'.format(CONF_DIR, cfg['AWS_ACCOUNT_ALIAS'])
STATE_FILE = '{0}/{1}.state'.format(HOME_DIR, cfg['AWS_ACCOUNT_ALIAS'])

TAGS_EXCLUDE_KEY_WORDS = ["Prod", "Production", "Do Not Stop"]

def _format_json(dictionary):
    return json.dumps(dictionary, indent=4, sort_keys=True)

def create_short_instances_dict(all_instances_dictionary):
    instance_dict ={}
    for region in all_instances_dictionary.items():
        if region[1]:
            try:
                state_list = region[1]["running"]
            except KeyError:
                state_list = region[1]["stopped"]
            instances_ids_list = []
            for instance in state_list:
                instances_ids_list.append(instance["ID"])
                instance_dict[region[0]] = instances_ids_list
    return instance_dict

def get_instance_tag():
    pass
class aws_ranger():    
    def __init__(self):
        ACCESS_KEY = cfg['AWS_ACCESS_KEY_ID']
        self.ACCESS_KEY = ACCESS_KEY

        SECRET_KEY = cfg['AWS_SECRET_ACCESS_KEY']
        self.SECRET_KEY = SECRET_KEY

    def aws_client(self, 
                   resource=True, 
                   region_name='eu-west-1', 
                   aws_service='ec2'):
        if resource:
            return boto3.resource(aws_service,
                                    aws_access_key_id=self.ACCESS_KEY,
                                    aws_secret_access_key=self.SECRET_KEY,
                                    region_name=region_name)
        else:
            return boto3.client(aws_service,
                                aws_access_key_id=self.ACCESS_KEY,
                                aws_secret_access_key=self.SECRET_KEY,
                                region_name=region_name)
        
    def _get_all_regions(self):
        region_list = []
        response = self.aws_client(resource=False).describe_regions()['Regions']
        for region in response:
            region_api_id = region['Endpoint'].split('.')[1]
            region_list.append(region_api_id)
        return region_list

    def fetch_instances(self, region=False):
        # instances =  self.aws_client(resource=False, region_name=region).describe_instances()
        instances =  self.aws_client(region_name=region).instances.filter(
            Filters=[])
        return instances

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
            instance_list = []
            excluded_instance_list = []
            running_instance_list = []
            stopped_instance_list = []
            region_inventory = {}
            instances = self.fetch_instances(region)
            for instance in instances:
                instance_dict = {}
                instance_dict['ID'] = instance.id
                instance_dict['Type'] = instance.instance_type
                instance_dict['Public DNS'] = instance.public_dns_name
                instance_dict['Creation Date'] = str(instance.launch_time)
                instance_dict['Tags'] = instance.tags
                instance_list.append(instance_dict)
                region_inventory[instance.state['Name']] = instance_list
            all_instances[region] = region_inventory
        return all_instances
    
    def create_state_file(self, dictionary):
        with open(STATE_FILE, 'w') as file:
            file.truncate()
            json.dump(dictionary, file, indent=4)
        pass

    def start_instnace(self, instance_list, region=False):
        for instance in instance_list:            
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=instance).start()

    def stop_instnace(self, instance_list, region=False):
        for instance in instance_list:            
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=instance).stop()

    def terminate_instnace(self, instance_list, region=False):
        for instance in instance_list:
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
@click.option('-v',
              '--verbose',
              is_flag=True,
              help="display run log in verbose mode")
@click.option('-d',
              '--debug',
              is_flag=True,
              help="debug new features")
def ranger(ctx, verbose, debug):
    """Round up your AWS instances

    Scout for Instances in all AWS Regions
    """
    ranger = aws_ranger()
    
    if debug:
        # timer = scheduler()
        # print timer.get_seconds_difference(timer.END_OF_DAY)
        ranger.create_state_file(ranger.get_instances())
        sys.exit()
    if verbose:
        logger.setLevel(logging.DEBUG)
    
    if ctx.invoked_subcommand is None:
        instances = create_short_instances_dict(ranger.get_instances())
        print instances
    else:
        pass

@ranger.command('stop')
@click.argument('region', default=False)
@click.option('-s',
              '--server',
              is_flag=True,
              help='Send the Ranger to Background')
def stop(region, server):
    """Stop instances Found by aws-ranger
    """
    ranger = aws_ranger()
    if server:
        # TODO: Impliment serv machenizem
        logger.info('Still not working')
        sys.exit()
    instances = ranger.get_instances()
    stop_list = create_short_instances_dict(instances)
    for k, v in stop_list.items():
        ranger.stop_instnace(v, region=k)

@ranger.command('terminate')
@click.argument('region', default=False)
@click.option('-s',
              '--server',
              is_flag=True,
              help='Send the Ranger to Background')
def terminate(region, server):
    """Terminate instances Found by aws-ranger
    """
    ranger = aws_ranger()
    if server:
        # TODO: Impliment serv machenizem
        logger.info('Still not working')
        sys.exit()
    instances = ranger.get_instances()
    stop_list = create_short_instances_dict(instances)
    for k, v in stop_list.items():
        ranger.terminate_instnace(v, region=k)

    instances = ranger.get_instances(instances_state="stopped")
    stop_list = create_short_instances_dict(instances)
    for k, v in stop_list.items():
        ranger.terminate_instnace(v, region=k)