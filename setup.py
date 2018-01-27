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
        'click==6.6',
        'boto3==1.4.4',
        'wryte==0.1.1',
        'psutil==5.4.3',
        'python-crontab==2.2.8',
    ]
)
