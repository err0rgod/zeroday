import boto3
client = boto3.client('logs', region_name='ap-south-2')
streams = client.describe_log_streams(logGroupName='/aws/lambda/zeroday-news-dev-api', orderBy='LastEventTime', descending=True, limit=1)
if streams['logStreams']:
    stream_name = streams['logStreams'][0]['logStreamName']
    print(f"Latest stream: {stream_name}")
    events = client.get_log_events(logGroupName='/aws/lambda/zeroday-news-dev-api', logStreamName=stream_name, limit=20, startFromHead=False)
    for e in events['events']:
        print(e['message'].strip())
else:
    print("No streams found.")
