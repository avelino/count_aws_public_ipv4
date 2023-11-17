import boto3
import configparser
import botocore

credentials = configparser.ConfigParser()
credentials.read('credentials.ini')
settings = configparser.ConfigParser()
settings.read('settings.ini')

# Organization Account
aws_organization_account = settings.get('settings', 'organization_account_section')

# AWS accounts to check, config the credentials.ini file
aws_accounts = {}

# If Empty, all regions will be checked
selected_regions=[]

# List to store All IPs
total_ips = []

# Iterate through each account in the credentials.ini file and set the aws_accounts dictionary
for section in credentials.sections():
    account = {
        'access_id': credentials.get(section, 'aws_access_key_id'),
        'access_key': credentials.get(section, 'aws_secret_access_key'),
        'session_token': credentials.get(section, 'aws_session_token'),
        'description': section
    }
    aws_accounts[section]=account

# AWS Organizations Account client to get the accounts names
organizations_client = boto3.client(
    'organizations',
    aws_access_key_id=aws_accounts[aws_organization_account]['access_id'],
    aws_secret_access_key=aws_accounts[aws_organization_account]['access_key'],
    aws_session_token=aws_accounts[aws_organization_account]['session_token']
)

# Iterate through each account in the credentials.ini file
for account_name, account in aws_accounts.items():

    # Dictionary to store the results for the account
    account_ips = []

    # Get the account id
    sts_client = boto3.client(
        'sts',
        aws_access_key_id=account['access_id'],
        aws_secret_access_key=account['access_key'],
        aws_session_token=account['session_token']
    )
    account_id = sts_client.get_caller_identity().get('Account')

    # Get the account name
    # If the account does not have permission to get the account name, it will print only the account id
    try:
        account_name = organizations_client.describe_account(AccountId=account_id).get('Account').get('Name')
        print(f"Account name: {account_name} ({account_id})")
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'AccessDeniedException':
            print(f"Account ({account_id}) - Access denied to get Account Name")
        else:
            raise e

    # Get the list of regions to check for the account
    # Use the selected_regions list if it is not empty
    if selected_regions:
        ec2_regions = selected_regions
    else:
        ec2_client = boto3.client(
            'ec2',
            region_name='us-east-2',
            aws_access_key_id=account['access_id'],
            aws_secret_access_key=account['access_key'],
            aws_session_token=account['session_token']
        )
        ec2_regions = [region['RegionName'] for region in ec2_client.describe_regions()['Regions']]

    # region_first is used only to format the output
    region_first = True
    # Iterate through each region in the AWS account
    for region in ec2_regions:
        # List to store the results for the region
        region_ips = []

        if region_first:
            region_first = False
            print("    Checking region:", end=" ")
        print(f"  {region}", sep=' ', end='', flush=True)

       # EC2 resource for the region
        ec2_resource = boto3.resource(
            'ec2',
            region_name=region,
            aws_access_key_id=account['access_id'],
            aws_secret_access_key=account['access_key'],
            aws_session_token=account['session_token']
        )

        # Get running instances.
        instances = ec2_resource.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
        # Iterate through each instance in the region
        for instance in instances:
            if instance.network_interfaces:
                # Iterate through each network interface in the instance
                for interface in instance.network_interfaces:
                    if interface.association_attribute:
                        # Check if the interface has a public IP
                        if interface.association_attribute.get('PublicIp'):
                            # Add the public IP to the list
                            region_ips.append(interface.association_attribute['PublicIp'])

        # Iterate through each elastic IP in the region
        for eip in ec2_resource.vpc_addresses.all():
            # Check if the elastic IP is associated with an instance
            # If it is not associated, it is added to the list
            if eip.public_ip not in region_ips:
                region_ips.append(eip.public_ip)

        # Store the results for the account and total
        account_ips += region_ips
        total_ips += region_ips
        print(f"({len(region_ips)})", end=' ', flush=True)

    # Print the results for the accounts and total
    print()
    print(f"        Total IPs for account: {len(account_ips)}")
    print("\n")
print(f"Total IPs for all accounts: {len(total_ips)}\n\n")
