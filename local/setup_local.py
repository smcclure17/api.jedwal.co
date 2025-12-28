"""Setup DynamoDB tables locally from CloudFormation template."""
import boto3
import yaml
from pathlib import Path

# Add custom constructors for CloudFormation intrinsic functions
def cfn_constructor(loader, node):
    """Generic constructor that returns the node value as-is."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)

# Register all common CloudFormation intrinsic functions
yaml.add_constructor('!Ref', cfn_constructor, Loader=yaml.SafeLoader)
yaml.add_constructor('!Sub', cfn_constructor, Loader=yaml.SafeLoader)
yaml.add_constructor('!GetAtt', cfn_constructor, Loader=yaml.SafeLoader)
yaml.add_constructor('!Join', cfn_constructor, Loader=yaml.SafeLoader)
yaml.add_constructor('!Select', cfn_constructor, Loader=yaml.SafeLoader)
yaml.add_constructor('!ImportValue', cfn_constructor, Loader=yaml.SafeLoader)

def get_dynamodb_client():
    return boto3.client(
        'dynamodb',
        endpoint_url='http://localhost:8001',
        region_name='local',
        aws_access_key_id='fake',
        aws_secret_access_key='fake'
    )

def create_table_from_cfn():
    """Parse CloudFormation and create DynamoDB table locally."""
    cfn_path = Path(__file__).parent.parent / 'cloudformation.yaml'
    
    with open(cfn_path) as f:
        cfn = yaml.safe_load(f)
    
    table_resource = cfn['Resources']['DynamoDBTableV2']['Properties']
    
    client = get_dynamodb_client()
    
    # Build create_table params from CloudFormation
    params = {
        'TableName': table_resource['TableName'],
        'AttributeDefinitions': table_resource['AttributeDefinitions'],
        'KeySchema': table_resource['KeySchema'],
        'BillingMode': table_resource['BillingMode'],
    }
    
    # Add GSIs if present
    if 'GlobalSecondaryIndexes' in table_resource:
        # Remove BillingMode from GSIs for local DynamoDB
        gsis = table_resource['GlobalSecondaryIndexes']
        for gsi in gsis:
            gsi.pop('BillingMode', None)
        params['GlobalSecondaryIndexes'] = gsis
    
    try:
        client.create_table(**params)
        print(f"✓ Created table: {params['TableName']}")
    except client.exceptions.ResourceInUseException:
        print(f"Table {params['TableName']} already exists")

if __name__ == '__main__':
    create_table_from_cfn()