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
        'boto3==1.4.4',
        'click==6.7',
        'Serv==0.3.0',
    ]
)
