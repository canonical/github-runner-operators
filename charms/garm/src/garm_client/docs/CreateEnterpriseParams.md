# CreateEnterpriseParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_mode** | **bool** |  | [optional] 
**credentials_name** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**pool_balancer_type** | **str** |  | [optional] 
**webhook_secret** | **str** |  | [optional] 

## Example

```python
from garm_client.models.create_enterprise_params import CreateEnterpriseParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateEnterpriseParams from a JSON string
create_enterprise_params_instance = CreateEnterpriseParams.from_json(json)
# print the JSON string representation of the object
print(CreateEnterpriseParams.to_json())

# convert the object into a dict
create_enterprise_params_dict = create_enterprise_params_instance.to_dict()
# create an instance of CreateEnterpriseParams from a dict
create_enterprise_params_from_dict = CreateEnterpriseParams.from_dict(create_enterprise_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


