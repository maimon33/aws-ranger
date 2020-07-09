import re
import os
import sys
import json
import socket
import difflib
import getpass
import time as Time

import smtplib
import urllib.request

from crontab import CronTab
from prettytable import PrettyTable
from datetime import time, date, timedelta, datetime

import boto3
import click

from wryte import Wryte
from botocore.exceptions import ClientError

import utils
from scheduler import Scheduler

CURRENT_FILE = sys.argv[0]
USERNAME = getpass.getuser()
USER_HOME = os.getenv("HOME")
HOSTNAME = socket.gethostname()

try:
    urllib.request.urlopen('http://www.google.com', timeout=1)
    PUBLIC_IP = json.load(urllib.request.urlopen('http://jsonip.com'))['ip']
except (urllib.error.URLError, socket.timeout):
    PUBLIC_IP = ""

ROLE_ARN = 'arn:aws:iam::{0}:role/aws-watcher'
AWS_RANGER_HOME = '{0}/.ranger'.format(USER_HOME)
BOTO_CREDENTIALS = '{0}/.aws/credentials'.format(USER_HOME)

def find_profiles(file=None):
    if not file:
        file = ""
    profiles_list = []
    try:
        boto_config = open(file).read()
        for match in re.findall("\[.*\]", boto_config):
            profiles_list.append(match.strip("[]"))
        return profiles_list
    except IOError:
        return ["default"]

def validate_ranger(ranger_home, config_path):
    if not os.path.exists(ranger_home):
        print(' Missing ranger HOME dir...\n Run:\n'\
              ' ranger --init or create it yourself at ~/.ranger')
        sys.exit()
    
    if not os.path.exists(config_path):
        print(' Missing ranger config...\n Run:\n'\
              ' ranger --init ')
        sys.exit()

def create_config_file(config_path, profile_name):
    aws_ranger_config = {}
    email_dictionary = {}
    
    # Config section

    # Tags
    default_exclude_tags = ["prod", "production", "free range"]
    tags_text = '\nPlease enter tag values to exclude them '\
            'from ranger (use comma to separate items) '\
            '\nDefaults = [prod, production, free range]: '
    exclude_tags = input(tags_text).split(",")
    if len(exclude_tags) == 0:
        exclude_tags = default_exclude_tags
    aws_ranger_config["EXCLUDE_TAGS"] = exclude_tags

    # Working Hours
    default_working_hours = {"First Day of the Week": "Sunday",
                             "Last Day of the Week": "Thursday",
                             "Start of working Day": "9",
                             "End of working Day": "18"}
    if utils._yes_or_no('\nDo you agree with these working hours? '\
                  '\n{} '.format(utils._format_json(default_working_hours))):
        working_hours = default_working_hours
        aws_ranger_config["Working Hours"] = working_hours
    else:
        first_day = input("First Day of the Week? [1-Sunday, 2-Monday] ")
        if first_day == 1:
            first_day = "Sunday"
        elif first_day == 2:
            first_day = "Monday"
        else:
            first_day = "Sunday"
        last_day = input("\nLast Day of the Week? [1-Thursday, 2-Friday] ")
        if last_day == 1:
            last_day = "Thursday"
        elif last == 2:
            last_day = "Friday"
        else:
            last_day = "Thursday"
        start_of_day = input("Start of working day? : ")
        end_of_day = input("End of working Day? (24H format) : ")
        
        working_hours = {"First Day of the Week": first_day,
                         "Last Day of the Week": last_day,
                         "Start of working Day": start_of_day,
                         "End of working Day": end_of_day}
        aws_ranger_config["Working Hours"] = working_hours

    # Email section
    if utils._yes_or_no('Setup Gmail?'):
        email_dictionary['GMAIL_ACCOUNT'] = input("\nGmail account? ")
        email_dictionary['GMAIL_PASSWORD'] = input("Gmail password? ")
        email_dictionary['DESTINATION_EMAIL'] = input("Destination? ")
        aws_ranger_config["EMAIL"] = email_dictionary
    
    with open(config_path, 'w') as file:
        json.dump(aws_ranger_config, file, indent=4)

def read_json_file_section(config_path, requested_data):
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
        
def create_short_instances_dict(all_instances_dictionary, 
                                execute_action, 
                                service=False):
    instance_dict ={}

    for region in all_instances_dictionary.items():
        instances_ids_list = []
        stopped_instances_ids = []
        running_instances_ids = []
        managed_instances_ids = []
        
        for instance in region[1]:
            if instance['ranger state'] == "excluded":
                continue
            
            if instance['State'] == "running" and \
                instance['ranger state'] != "managed":
                running_instances_ids.append(instance["_ID"])

            if instance['State'] in ["running", "stopped"] and \
                instance['ranger state'] == "managed":
                managed_instances_ids.append(instance["_ID"])

            if instance['State'] == "stopped":
                stopped_instances_ids.append(instance["_ID"])

        if service:
            instance_dict[region[0]] = managed_instances_ids
        else:
            if execute_action == "start":
                instances_ids_list = managed_instances_ids + \
                                     stopped_instances_ids
                instance_dict[region[0]] = instances_ids_list
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

def create_state_dictionary(dictionary):
    state_file_dictionary = {}

    for region in dictionary.items():
        region_instances = []

        for instance in region[1]:
            if instance['ranger state'] == "excluded":
                region_instances.append(instance)
            elif instance['State'] == "running":
                instance['ranger state'] = "managed"
                region_instances.append(instance)
            elif instance['State'] == "stopped" and \
                instance['ranger state'] != "managed":
                instance['ranger state'] = "ignored"
                region_instances.append(instance)
        state_file_dictionary[region[0]] = region_instances
    return state_file_dictionary

def confirm_state_file(file_path):
    try:
        state_file = read_json_file(file_path)
        schedule = state_file['_schedule']
        return True
    except ValueError:
        print(' State file corrupted. Create new by using --init\n ')
        sys.exit()
    except KeyError:
        print("Missing schedule config. Run again with --init flag")
        sys.exit()
    except IOError:
        print("missing state file")
        sys.exit()

def read_json_file(json_file):
    try:
        return json.load(open(json_file))
    except IOError:
        return "File Missing"

def update_json_file(file_path, new_dictionary):
    try:
        orig_state_file = json.load(open(file_path))
    except (IOError, ValueError):
        orig_state_file = {}
    orig_state_file.update(new_dictionary)
    with open(file_path, 'w') as file:
        json.dump(orig_state_file, file, indent=4, sort_keys=True)

def update_instances_state_file(state_file, all_instances_dictionary):
    new_state_dict = {}
    instances_list = []
    current_instances_ids = []
    state_file_instances_ids = []

    state_dict = read_json_file(state_file)
    instances = create_state_dictionary(all_instances_dictionary)

    # Remove Schedule section for state evaluation
    state_dict.pop('_schedule', None)

    for region, state_instances_list in state_dict.items():
        for state_instance in state_instances_list:
            try:
                state_file_instances_ids.append(state_instance["_ID"])
            except TypeError:
                pass

    for region, current_instances_list in instances.items():
        for instance in current_instances_list:
            if instance["_ID"] in state_file_instances_ids:
                for state_instance in state_instances_list:
                    if state_instance["_ID"] == instance["_ID"]:
                        instances_list.append(state_instance)
            else:
                if instance['ranger state'] == "excluded":
                    instances_list.append(instance)
                elif instance["State"] == "running":
                    instance['ranger state'] == "managed"
                    instances_list.append(instance)
                elif instance["State"] == "stopped" and \
                    instance['ranger state'] != "managed":
                    instance['ranger state'] == "ignored"
                    instances_list.append(instance)
        new_state_dict[region] = instances_list
        update_dictionary(state_file, region, new_state_dict[region])

def update_instance_state(state_file, target_instances, key, value):
    state_dict = read_json_file(state_file)

    # Remove Schedule section for state evaluation
    schedule_info = state_dict['_schedule']
    state_dict.pop('_schedule', None)

    for region, state_instances_list in state_dict.items():
        for state_instance in state_instances_list:
            for instances in target_instances:
                if state_instance["_ID"] == instances:
                    try:
                        state_instance[key] = value
                    except KeyError:
                        pass
    
    state_dict['_schedule'] = schedule_info
    update_json_file(state_file, state_dict)

def remove_instance_from_state(state_file, region, target_instance):
    state_dict = read_json_file(state_file)

    # Remove Schedule section for state evaluation
    schedule_info = state_dict['_schedule']
    state_dict.pop('_schedule', None)

    for region, state_instances_list in state_dict.items():
        for state_instance in state_instances_list:
            if target_instance == state_instance["_ID"]:
                state_instances_list.remove(state_instance)

    state_dict['_schedule'] = schedule_info
    update_json_file(state_file, state_dict)

def update_dictionary(file_path, section, keys_and_values):
    try:
        state_file = json.load(open(file_path))
    except ValueError:
        print("Corrupted json file")
        sys.exit()
    state_file[section] = keys_and_values
    with open(file_path, 'w') as file:
        json.dump(state_file, file, indent=4, sort_keys=True)

def assume_aws_role(accountid):
    try:
        response = boto3.client("sts").assume_role(DurationSeconds=3600, 
                                                ExternalId="watcher-temp",
                                                RoleArn=ROLE_ARN.format(accountid),
                                                RoleSessionName="Watcher")
        os.environ["AWS_ACCESS_KEY_ID"] = response["Credentials"]["AccessKeyId"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = response["Credentials"]["SecretAccessKey"]
        os.environ["AWS_SESSION_TOKEN"] = response["Credentials"]["SessionToken"]
    except ClientError as e:
        print('Unable to Assume role\n'
        'Review to origin Creds [IAM role, AWS keys]')
        sys.exit()

def get_current_account_id():
    return boto3.client('sts').get_caller_identity().get('Account')

class AWSRanger(object):
    def __init__(self, profile_name):
        try:
            self.aws_client(resource=False, 
                            profile_name=None).describe_regions()
        except ClientError as e:
            print('Failed to Authenticate your AWS account\n'
            'Review your boto credentials file at ~/.aws/credentials')
            sys.exit()

    def aws_client(self, 
                   resource=True,
                   profile_name=None,
                   region_name="eu-west-1",
                   aws_service="ec2"):
        
        if not profile_name:
            session = boto3.Session()
        else:
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

    def convert_region_name(self, region_endpoint):
        return self.aws_client(resource=False, aws_service="ssm").get_parameter(
            Name='/aws/service/global-infrastructure/regions/{}/longName'.format(
                region_endpoint))['Parameter']['Value']

    def get_instance_os(self, region, instanceid):
        instance = self.aws_client(
            resource=False,
            region_name=region).describe_instances(Filters=[{'Name': 'instance-id', 'Values': [instanceid]}])
        instance_ami = instance["Reservations"][0]["Instances"][0]["ImageId"]
        ami_os = self.aws_client(
            resource=False,
            region_name=region).describe_images(Filters=[{'Name': 'image-id', 'Values': [instance_ami]}])
        try:
            return ami_os["Images"][0]["PlatformDetails"].split("/")[0]
        except KeyError:
            return ami_os["Images"][0]["Name"].split("/")[0]
    
    def get_price(self, region, instance, os):
        FLT = '[{{"Field": "tenancy", "Value": "shared", "Type": "TERM_MATCH"}},'\
            '{{"Field": "operatingSystem", "Value": "{o}", "Type": "TERM_MATCH"}},'\
            '{{"Field": "preInstalledSw", "Value": "NA", "Type": "TERM_MATCH"}},'\
            '{{"Field": "instanceType", "Value": "{t}", "Type": "TERM_MATCH"}},'\
            '{{"Field": "locationType", "Value": "AWS Region", "Type": "TERM_MATCH"}},'\
            '{{"Field": "capacitystatus", "Value": "Used", "Type": "TERM_MATCH"}}]'

        f = FLT.format(t=instance, o=os)
        data = self.aws_client(
            resource=False, 
            region_name='us-east-1', 
            aws_service='pricing').get_products(
                ServiceCode='AmazonEC2', Filters=json.loads(f))
        od = json.loads(data['PriceList'][0])['terms']['OnDemand']
        id1 = list(od)[0]
        id2 = list(od[id1]['priceDimensions'])[0]
        return od[id1]['priceDimensions'][id2]['pricePerUnit']['USD']

    def fetch_instances(self, instance_state, region=False):
        return self.aws_client(region_name=region).instances.filter(
            Filters=[{'Name': 'instance-state-name', 
                      'Values': instance_state}])

    def get_instances(self,
                      config_path, 
                      instances_state=["running", "stopped"],
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
                    print("Skipping region: {}".format(region))

        all_instances = {}

        for region in region_list:
            instances_list = []
            region_inventory = {}
            
            instances = self.fetch_instances(instances_state, region)
            for instance in instances:
                instance_dict = {}
                instance_dict['_ID'] = instance.id
                instance_dict['State'] = instance.state['Name']
                instance_dict['Type'] = instance.instance_type
                instance_cost = self.get_price(region, instance.instance_type, self.get_instance_os(region, instance.id))
                instance_dict['Cost per hour'] = instance_cost
                instance_dict['Public DNS'] = instance.public_dns_name
                instance_dict['Creation Date'] = str(instance.launch_time)
                instance_dict['ranger state'] = "new"
                instance_dict['Tags'] = instance.tags
                
                try:
                    if instance.tags[0]['Value'].lower() in \
                    read_json_file_section(config_path, "EXCLUDE_TAGS"):
                        instance_dict['ranger state'] = "excluded"
                        instances_list.append(instance_dict)
                        continue
                except TypeError:
                    instance_dict['Tags'] = [{u'Value': 'none', u'Key': 'Tag'}]

                instances_list.append(instance_dict)
            all_instances[region] = instances_list
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
                    state_file,
                    instances,
                    region=False,
                    action="pass",
                    cron=False):
        
        tags_list = [{"Key":"ranger Host", 
                      "Value":"{0} @ {1}".format(HOSTNAME, PUBLIC_IP)},
                     {"Key":"ranger Last Action",
                      "Value":"{0} @ {1}".format(
                          action, Time.strftime("%Y-%m-%d %H:%M:%S"))},
                     {"Key":"ranger User",
                      "Value":USERNAME}]
        
        try:
            if action.lower() == 'stop':
                if cron:
                    stop_dictionary = instances
                else:
                    stop_dictionary = create_short_instances_dict(
                        instances, action.lower())
                for k, v in stop_dictionary.items():
                    self.stop_instnace(v, region=k)
                    self.update_tags(v, tags_list, region=k)
                    if cron:
                        update_instance_state(state_file, v, "State", "stopped")
            elif action.lower() == 'start':
                if cron:
                    start_dictionary = instances
                else:
                    start_dictionary = create_short_instances_dict(
                        instances, action.lower())
                for k, v in start_dictionary.items():
                    self.start_instnace(v, region=k)
                    self.update_tags(v, tags_list, region=k)
                    if cron:
                        update_instance_state(state_file, v, "State", "running")
            elif action.lower() == 'terminate':
                if cron:
                    terminate_dictionary = instances
                else:
                    terminate_dictionary = create_short_instances_dict(
                        instances, action.lower())
                for k, v in terminate_dictionary.items():
                    self.terminate_instnace(v, region=k)
                    if cron:
                        remove_instance_from_state(state_file, k, v)
                        pass
            elif action == 'pass':
                pass
        except AttributeError:
            pass
        except ClientError:
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
              help="Config ranger for first use")
@click.option('-a',
              '--accounts',
              help=' Privide a list of accounts to inspect')              
@click.option('-r',
              '--region',
              default="eu-west-1",
              help=' Specify the region\n'\
                   ' Default to "eu-west-1"')
@click.option('-x',
              '--execute',
              help=' What action to carry out on instances not protected?   \b'
                   ' Stop, Start or Terminate ')
@click.option('-t',
              '--table',
              is_flag=True,
              help='prints output in table format')
def ranger(ctx, init, accounts, region, execute, table):
    """Round up your AWS instances

    Scout for Instances in all AWS Regions
    """

    if not utils._internet_on():
        print("No Internet connection...")
        sys.exit()
    
    DEFAULT_AWS_PROFILE = find_profiles(BOTO_CREDENTIALS)[0]
    CONFIG_PATH = '{0}/{1}.conf'.format(AWS_RANGER_HOME,
                                        DEFAULT_AWS_PROFILE)
    STATE_FILE = '{0}/{1}.state'.format(AWS_RANGER_HOME,
                                        DEFAULT_AWS_PROFILE)

    if init:
        if os.path.exists(AWS_RANGER_HOME):
            print("ranger Home exists, checking config...")
            if os.path.exists(CONFIG_PATH):
                if utils._yes_or_no(' ranger was already initiated, '\
                              ' Overwrite config? '):
                    utils._safe_remove(CONFIG_PATH)
                    create_config_file(CONFIG_PATH, DEFAULT_AWS_PROFILE)
            else:
                print("Creating ranger config file")
                create_config_file(CONFIG_PATH, DEFAULT_AWS_PROFILE)
        else:
            if utils._yes_or_no(' You are about to create Home dir for ranger.\n '
                          ' Continue? '):
                os.makedirs(AWS_RANGER_HOME)
                create_config_file(CONFIG_PATH, DEFAULT_AWS_PROFILE)
    
    validate_ranger(AWS_RANGER_HOME, CONFIG_PATH)

    if region == "all":
        all_regions = True
    else:
        all_regions = False

    if not accounts:
        accounts = [get_current_account_id()]
    else:
        accounts = eval(accounts)

    for account in accounts:
        if len(accounts) > 1:
            assume_aws_role(account)

        # TODO: 
        # logger starts here. tries to read the transaction #, increments when
        # found and later used by the logger 
        
        ranger = AWSRanger(profile_name=DEFAULT_AWS_PROFILE)

        if all_regions:
            region = None
        
        instances = {}
        instances = ranger.get_instances(CONFIG_PATH, region=region)
        
        if ctx.invoked_subcommand:
            pass
        else:
            ranger.executioner(CONFIG_PATH, STATE_FILE, instances, action=execute)
        
        if ctx.invoked_subcommand is None and not execute:
            if table:
                print("Summery for Account ID: {}".format(account))
                x = PrettyTable()
                x.field_names = ["AWS Region", "# of instances"]
                if all_regions:
                    for region in ranger.get_all_regions():
                        if len(instances[region]) > 0:
                            x.add_row([ranger.convert_region_name(region), len(instances[region])])
                else:
                    if len(instances[region]) > 0:
                        x.add_row([ranger.convert_region_name(region), len(instances[region])])
                    else:
                        print("Region has no instance")
                print(x)
            else:
                print(utils._format_json(instances))

        ctx.obj = [DEFAULT_AWS_PROFILE, CONFIG_PATH, STATE_FILE, instances, region]

@ranger.command('cron')
@click.pass_obj
@click.option('--init',
              is_flag=True,
              help='Sets cron, insert _schedule key to state_file '
                   'Configures schedule section and policy')
@click.option('-p',
              '--policy',
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
              help='Remove ranger from cron')
def cron(ctx, policy, execute, init, stop):
    """Run ranger as a cron job.\n
    
    \b 
    Control ranger by setting the policy,
    [nightly]: Executes (stop\ terminate) on Instances every end of day
    [workweek]: Executes (stop\ terminate) on Instances just before the weekend
    [full]: Executes (stop\ start) on Instances Daily and over the weekend

    Set the Execution that ranger will enforce [stop, terminate, alert]\n
    You can limit ranger control to one region.\n
    """
    DEFAULT_AWS_PROFILE = ctx[0]
    CONFIG_PATH = ctx[1]
    STATE_FILE = ctx[2]
    instances = ctx[3]
    region = ctx[4]
   
    if stop:
        utils._kill_process("ranger")
        utils._config_cronjob("unset", comment="ranger")
        utils._safe_remove(STATE_FILE)
        sys.exit()
    
    if utils._find_duplicate_processes("ranger"):
        print("ranger already running! quiting...")
        sys.exit()

    if policy not in ['nightly', 'workweek', 'full']:
        print("Policy not Found! Review and select one of three"\
        " Selecting 'full'")
        policy = "full"

    if policy.lower() == "full":
        execute = "stop"

    args = '-r {0} {1} -p {2} -x {3}'.format(region, "cron", policy, execute)
    
    validate_ranger(AWS_RANGER_HOME, CONFIG_PATH)
    
    scheduler = Scheduler(config_path=CONFIG_PATH, state_file=STATE_FILE)
    
    if init:
        if os.path.isfile(STATE_FILE):
            if utils._yes_or_no("State file exists, Do you want to overwrite it?"):
                utils._safe_remove(STATE_FILE)
                update_json_file(STATE_FILE, create_state_dictionary(instances))
                schedule_info = scheduler.get_schedule_section(policy,
                                                               execute)
                update_dictionary(STATE_FILE, "_schedule", schedule_info)
                utils._config_cronjob("set",
                                command=CURRENT_FILE,
                                args=args,
                                comment="ranger")
            else:
                print("Aborting! you must add schedule section into state file")
                sys.exit()
        else:
            print("Creating ranger state file")
            update_json_file(STATE_FILE, create_state_dictionary(instances))
            schedule_info = scheduler.get_schedule_section(policy,
                                                           execute)
            update_dictionary(STATE_FILE, "_schedule", schedule_info)
            utils._config_cronjob("set",
                            command=CURRENT_FILE,
                            args=args,
                            comment="ranger")
    
    if confirm_state_file(STATE_FILE):
        scheduler.cron_run(DEFAULT_AWS_PROFILE,
                           CONFIG_PATH,
                           STATE_FILE,
                           region,
                           policy,
                           execute,
                           instances)
    else:
        print("State file missing or corrupted. run `ranger cron --init`")
        sys.exit()
