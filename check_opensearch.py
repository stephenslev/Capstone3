# check_opensearch.py
import os
import boto3
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

load_dotenv()

host = os.environ["OPENSEARCH_ENDPOINT"]   # no https://
region = "us-east-1"                       # your region
credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, region, "es")  # "aoss" for Serverless

client = OpenSearch(
    hosts=[{"host": host, "port": 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
)

result = client.count(index="documents")
print("Document count:", result["count"])