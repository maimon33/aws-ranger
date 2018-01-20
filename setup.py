from setuptools import setup

setup(
    name='aws-ranger',
    version='0.1.0',
    author='Assi Maimon',
    author_email='maimon33@gmail.com',
    py_modules=['aws-ranger'],
    description='Control your AWS instances',
    entry_points={
        'console_scripts': [
                'aws-ranger=aws_ranger:ranger',
        ],
    },
    install_requires=[
        'click==6.7',
        'Serv==0.3.0',
        'boto3==1.4.4',
        'crontab==0.22.0',
        'APScheduler==3.5.1',
        'python-daemon-2.1.2',
    ]
)
