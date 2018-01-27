## aws-ranger

**WIP**<br>
Some features are not fully operational yet

The tool to help you get a handle on your AWS account.

To start using just type: `aws-ranger --init`.<br>
This will prompt for your AWS creds and account alias of your choice and map your entire account.

You later could run it again but with an action: `stop, start` OR `terminate`


#### Install
`pip install https://github.com/maimon33/aws-ranger/archive/master.zip`

#### Basic usage
* get current state
```
$ aws-ranger
Did not receive action to execute. printing current state
{
    "ap-northeast-1": {}, 
    "ap-northeast-2": {}, 
    "ap-south-1": {}, 
    "ap-southeast-1": {}, 
    "ap-southeast-2": {}, 
    "ca-central-1": {}, 
    "eu-central-1": {}, 
    "eu-west-1": {}, 
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

#### Daemon mode

**not operational!**<br>
You can have aws-ranger run in the background and control your instance on a time windows basis.<br>
Stop all instances out of working hours.<br>
_you can exclude instances based on tags_