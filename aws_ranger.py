import os
import json
import logging

import serv
import boto3
import click

from botocore.exceptions import ClientError

# Setting up a logger
logger = logging.getLogger('AWS ranger')
logger.setLevel(logging.INFO)
console = logging.StreamHandler()
logger.addHandler(console)


CONFIG_PATH = '{0}/.aws-ranger/aws-creds/{1}.json'.format(os.getenv("HOME"), 'aws')

try:
    if not os.path.exists('{0}/.aws-ranger/aws-creds'.format(os.getenv("HOME"))):
        os.makedirs('{0}/.aws-ranger/aws-creds'.format(os.getenv("HOME")))
except OSError:
    print "Error Creating config folder"

def _format_json(dictionary):
    return json.dumps(dictionary, indent=4, sort_keys=True)

def _config():
    print "Please provide Authentication details"
    AWS_ACCESS_KEY_ID=raw_input('Enter Your Gmail Account Name : ')
    AWS_SECRET_ACCESS_KEY=raw_input('Enter Your Gmail Account Password : ')
    config = {"aws-account": {'AWS_ACCESS_KEY_ID': AWS_ACCESS_KEY_ID, 'AWS_SECRET_ACCESS_KEY': AWS_SECRET_ACCESS_KEY}}
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f)
        
if os.path.isfile(CONFIG_PATH):
    pass
else:
    print "Missing AWS creds"
    _config()

def create_short_instances_dict(all_instances_dictionary):
    instance_dict ={}
    for region in all_instances_dictionary.items():
        if region[1]:
            region_list = region[1][region[0]]
            instances_ids_list = []
            for instance in region_list:
                instances_ids_list.append(region[1][region[0]][0]["ID"])
                instance_dict[region[0]] = instances_ids_list
    return instance_dict

class aws_ranger():    

    def __init__(self):
        with open(CONFIG_PATH) as config_file:
            cfg = json.load(config_file)["aws-account"]

        ACCESS_KEY = cfg['AWS_ACCESS_KEY_ID']
        self.ACCESS_KEY = ACCESS_KEY

        SECRET_KEY = cfg['AWS_SECRET_ACCESS_KEY']
        self.SECRET_KEY = SECRET_KEY

    def aws_client(self, resource=True, region_name='eu-west-1', aws_service='ec2'):
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

    def get_running_instances(self, region=False):
        all_instances = []
        region_list = []

        if region:
            region_list.append(region)
        else:
            for region in self._get_all_regions():
                region_list.append(region)

        all_instances = {}
        for region in region_list:
            instance_list = []
            region_inventory = {}
            instances = self.aws_client(region_name=region).instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
            for instance in instances:
                instance_dict = {}
                instance_dict['ID'] = instance.id
                instance_dict['Type'] = instance.instance_type
                instance_dict['Public DNS'] = instance.public_dns_name
                instance_dict['Creation Date'] = str(instance.launch_time)
                instance_dict['Tags'] = instance.tags
                instance_list.append(instance_dict)
                region_inventory[region] = instance_list
            all_instances[region] = region_inventory
        return all_instances

    def stop_instnace(self, instance_list, region=False):
        self.aws_client(region_name=region).instances.filter(InstanceIds=instance_list).stop()


CLICK_CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    token_normalize_func=lambda param: param.lower(),
    ignore_unknown_options=True)

@click.command(context_settings=CLICK_CONTEXT_SETTINGS)
@click.argument('region', default=False)
@click.option('-s',
              '--server',
              is_flag=True,
              help='Send the Ranger to Background?')
@click.option('-v',
              '--verbose',
              is_flag=True,
              help="display run log in verbose mode")
@click.option('-d',
              '--debug',
              is_flag=True,
              help="debug new features")
def ranger(distro, server, verbose, debug):
    """Round up your AWS instances
    """
    ranger = aws_ranger()
    
    if debug:
        print "Hi"
        find_ami()
        sys.exit()
    if verbose:
        logger.setLevel(logging.DEBUG)
    if server:
        # Impliment serv machenizem
        pass
    else:
        instances = ranger.get_running_instances()
        print instances
        stop_list = create_short_instances_dict(instances)
        print stop_list
        # for k, v in stop_list.items():
        #     ranger.stop_instnace(v, region=k)