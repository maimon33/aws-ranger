## ranger

The tool to help you get a handle on your AWS account.


Before using ranger, you'll need to configure boto3 or have run from an
 instance with the proper IAM role.<br>
You have several options for that: [boto3 Docs](http://boto3.readthedocs.io/en/latest/guide/configuration.html)

Once boto3 is configured, Start using ranger by initializing it.
Type: `ranger --init`.<br>

You later could run it again but with an action: `stop, start` OR `terminate`<br>
Use the `-x` flag


## Install
`pip install https://github.com/maimon33/ranger/archive/master.zip`

## Basic usage
* get current to default region
```
$ ranger
{
    "eu-west-1": {}
}
```
* get current to all regions
```
$ ranger -r all
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
$ ranger -x terminate
Terminating instance: i-0c08a1631d92268e4
Terminating instance: i-0da0f947e9dc1cac8
Terminating instance: i-054c4adfb5d06e3de
Terminating instance: i-0c54eaa6746f91b63
```

## Cron mode

To Set the cronjob to run ranger every minute simply run the init command `ranger cron --init`<br> 
_This command relies on ranger being initiated first_<br>

As before you have the option of stopping or terminating instances controlled by ranger.<br>

**In the cron mode you'll need to set the policy too**<br>
The policy will determine when and ranger action will be executed automatically.
* **Nightly**: Stops or Terminates instances at the end of the day
* **Workweek**: Stops or Terminates instances just before the weekend
* **Full**: Stops instances Nightly and Starts them up at the start of the next weekday

Use `-p` flag and Specify the policy you'd like to enforce and
 `-x` for the action to be executed<br>
**Default action  and policy for the cron mode is "Stop" and "Nightly"**

* Start ranger cron
```
$ ranger cron --init
Creating ranger state file
```

* Stop aws-ranger cron
```
$ ranger cron -s
Removing ranger job
```