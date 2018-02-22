## aws-ranger

**WIP**<br>
Some features are not fully operational yet

The tool to help you get a handle on your AWS account.

To start using just type: `aws-ranger --init`.<br>
This will prompt for your AWS creds and account alias of your choice and map your entire account.

You later could run it again but with an action: `stop, start` OR `terminate`


### Install
`pip install https://github.com/maimon33/aws-ranger/archive/master.zip`

### Basic usage
* get current to default region

```
$ aws-ranger
{
    "eu-west-1": {}
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

### Cron mode

**not operational!**<br>
You can have aws-ranger run in by cron and control your instance continuously.<br>
Stop all instances out of working hours.<br>
_you can exclude instances based on tags_