# Instance


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**addresses** | [**List[Address]**](Address.md) | Addresses is a list of IP addresses the provider reports for this instance. | [optional] 
**agent_id** | **int** | AgentID is the github runner agent ID. | [optional] 
**capabilities** | [**AgentCapabilities**](AgentCapabilities.md) |  | [optional] 
**created_at** | **datetime** | CreatedAt is the timestamp of the creation of this runner. | [optional] 
**generation** | **int** | Generation is the pool generation at the time of creating this instance. This field is to track a divergence between when the instance was created and the settings currently set on a pool. We can then use this field to know if the instance is out of date with the pool, allowing us to remove it if we need to. | [optional] 
**github_runner_group** | **str** | GithubRunnerGroup is the github runner group to which the runner belongs. The runner group must be created by someone with access to the enterprise. | [optional] 
**heartbeat** | **datetime** | Heartbeat is the last recorded heartbeat from the runner | [optional] 
**id** | **str** | ID is the database ID of this instance. | [optional] 
**job** | [**Job**](Job.md) |  | [optional] 
**name** | **str** | Name is the name associated with an instance. Depending on the provider, this may or may not be useful in the context of the provider, but we can use it internally to identify the instance. | [optional] 
**os_arch** | **str** |  | [optional] 
**os_name** | **str** | OSName is the name of the OS. Eg: ubuntu, centos, etc. | [optional] 
**os_type** | **str** |  | [optional] 
**os_version** | **str** | OSVersion is the version of the operating system. | [optional] 
**pool_id** | **str** | PoolID is the ID of the garm pool to which a runner belongs. | [optional] 
**provider_fault** | **List[int]** | ProviderFault holds any error messages captured from the IaaS provider that is responsible for managing the lifecycle of the runner. | [optional] 
**provider_id** | **str** | PeoviderID is the unique ID the provider associated with the compute instance. We use this to identify the instance in the provider. | [optional] 
**provider_name** | **str** | ProviderName is the name of the IaaS where the instance was created. | [optional] 
**runner_status** | **str** |  | [optional] 
**scale_set_id** | **int** | ScaleSetID is the ID of the scale set to which a runner belongs. | [optional] 
**status** | **str** |  | [optional] 
**status_messages** | [**List[StatusMessage]**](StatusMessage.md) | StatusMessages is a list of status messages sent back by the runner as it sets itself up. | [optional] 
**updated_at** | **datetime** | UpdatedAt is the timestamp of the last update to this runner. | [optional] 

## Example

```python
from garm_client.models.instance import Instance

# TODO update the JSON string below
json = "{}"
# create an instance of Instance from a JSON string
instance_instance = Instance.from_json(json)
# print the JSON string representation of the object
print(Instance.to_json())

# convert the object into a dict
instance_dict = instance_instance.to_dict()
# create an instance of Instance from a dict
instance_from_dict = Instance.from_dict(instance_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


