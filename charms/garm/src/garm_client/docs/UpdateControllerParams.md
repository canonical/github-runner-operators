# UpdateControllerParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_url** | **str** |  | [optional] 
**ca_cert_bundle** | **List[int]** |  | [optional] 
**callback_url** | **str** |  | [optional] 
**clear_ca_cert_bundle** | **bool** |  | [optional] 
**enable_agent_tools_sync** | **bool** |  | [optional] 
**garm_agent_releases_url** | **str** |  | [optional] 
**metadata_url** | **str** |  | [optional] 
**minimum_job_age_backoff** | **int** |  | [optional] 
**webhook_url** | **str** |  | [optional] 

## Example

```python
from garm_client.models.update_controller_params import UpdateControllerParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateControllerParams from a JSON string
update_controller_params_instance = UpdateControllerParams.from_json(json)
# print the JSON string representation of the object
print(UpdateControllerParams.to_json())

# convert the object into a dict
update_controller_params_dict = update_controller_params_instance.to_dict()
# create an instance of UpdateControllerParams from a dict
update_controller_params_from_dict = UpdateControllerParams.from_dict(update_controller_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


