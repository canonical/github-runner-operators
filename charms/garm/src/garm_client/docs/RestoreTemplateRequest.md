# RestoreTemplateRequest


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**forge** | **str** |  | [optional] 
**os_type** | **str** |  | [optional] 
**restore_all** | **bool** | RestoreAll indicates whether or not to restore all known system owned templates. If set, the Forge and OSType params are ignored. | [optional] 

## Example

```python
from garm_client.models.restore_template_request import RestoreTemplateRequest

# TODO update the JSON string below
json = "{}"
# create an instance of RestoreTemplateRequest from a JSON string
restore_template_request_instance = RestoreTemplateRequest.from_json(json)
# print the JSON string representation of the object
print(RestoreTemplateRequest.to_json())

# convert the object into a dict
restore_template_request_dict = restore_template_request_instance.to_dict()
# create an instance of RestoreTemplateRequest from a dict
restore_template_request_from_dict = RestoreTemplateRequest.from_dict(restore_template_request_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


