# CreateRepoParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_mode** | **bool** |  | [optional] 
**credentials_name** | **str** |  | [optional] 
**forge_type** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**owner** | **str** |  | [optional] 
**pool_balancer_type** | **str** |  | [optional] 
**webhook_secret** | **str** |  | [optional] 

## Example

```python
from garm_client.models.create_repo_params import CreateRepoParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateRepoParams from a JSON string
create_repo_params_instance = CreateRepoParams.from_json(json)
# print the JSON string representation of the object
print(CreateRepoParams.to_json())

# convert the object into a dict
create_repo_params_dict = create_repo_params_instance.to_dict()
# create an instance of CreateRepoParams from a dict
create_repo_params_from_dict = CreateRepoParams.from_dict(create_repo_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


