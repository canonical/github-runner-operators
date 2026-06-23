# StatusMessage


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**created_at** | **datetime** |  | [optional] 
**event_level** | **str** |  | [optional] 
**event_type** | **str** |  | [optional] 
**message** | **str** |  | [optional] 

## Example

```python
from garm_client.models.status_message import StatusMessage

# TODO update the JSON string below
json = "{}"
# create an instance of StatusMessage from a JSON string
status_message_instance = StatusMessage.from_json(json)
# print the JSON string representation of the object
print(StatusMessage.to_json())

# convert the object into a dict
status_message_dict = status_message_instance.to_dict()
# create an instance of StatusMessage from a dict
status_message_from_dict = StatusMessage.from_dict(status_message_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


