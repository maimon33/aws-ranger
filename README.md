## aws-ranger

**WIP**<br>
Some features are not fully operational yet

The tool to help you get a handle on your AWS account.

To start using just type: `aws-ranger --init`.<br>
This will prompt for your AWS creds and account alias of your choice and map your entire account.

You later could run it again but with an action: `stop, start` OR `terminate`


## Install
`pip install https://github.com/maimon33/aws-ranger/archive/master.zip`

## Basic usage
* get current to default region
```
$ aws-ranger
{
    "eu-west-1": {}
}
```
* get current to all regions
```
$ aws-ranger -r all
{
    "ap-northeast-1": {}, 
    "ap-northeast-2": {}, 
    "ap-south-1": {}, 
    "ap-southeast-1": {}, 
    "ap-southeast-2": {}, 
    "ca-central-1": {}, 
    "eu-central-1": {}, 
    "eu-west-1": {
        "stopped": [
            {
                "Creation Date": "2018-02-20 12:00:32+00:00", 
                "Public DNS": "", 
                "State": "stopped", 
                "Tags": [
                    {
                        "Key": "aws-ranger User", 
                        "Value": "assi"
                    }, 
                    {
                        "Key": "aws-ranger Host", 
                        "Value": "assi-Vostro-3300 @ 1.1.2.2"
                    }, 
                    {
                        "Key": "aws-ranger Last Action", 
                        "Value": "stop @ 2018-02-20 14:01:18"
                    }
                ], 
                "Type": "t2.medium", 
                "_ID": "i-041c950e75616046e"
            }
        ]
    }, 
    "eu-west-2": {}, 
    "eu-west-3": {}, 
    "sa-east-1": {}, 
    "us-east-1": {}, 
    "us-east-2": {}, 
    "us-west-1": {}, 
    "us-west-2": {}
}
```
* terminate instances without protected tags
```
$ aws-ranger -x terminate
Terminating instance: i-0c08a1631d92268e4
Terminating instance: i-0da0f947e9dc1cac8
Terminating instance: i-054c4adfb5d06e3de
Terminating instance: i-0c54eaa6746f91b63
```

## Cron mode

To Set the cronjob to run aws-ranger every minute simply run the init command. This command relies on aws-ranger being initiated first
* Start aws-ranger cron
```
$ aws-ranger cron --init
Creating aws-ranger state file
```

* Stop aws-ranger cron
```
$ aws-ranger cron -s
Removing aws-ranger job
```