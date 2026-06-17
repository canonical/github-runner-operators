# InstanceMetadata


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_mode** | **bool** | Agent mode indicates whether or not we need to install the GARM agent on the runner. | [optional] 
**agent_shell_enabled** | **bool** |  | [optional] 
**agent_token** | **str** |  | [optional] 
**agent_tools** | [**GARMAgentTool**](GARMAgentTool.md) |  | [optional] 
**ca_bundles** | **Dict[str, List[int]]** |  | [optional] 
**extra_specs** | **Dict[str, object]** | ExtraSpecs represents the extra specs set on the pool or scale set. No secrets should be set in extra specs. Also, the instance metadata should never be saved to disk, and the metadata URL is only accessible during setup of the runner. The API returns unauthorized once the runner transitions to failed/idle. | [optional] 
**forge_type** | **str** |  | [optional] 
**jit_enabled** | **bool** |  | [optional] 
**metadata_access** | [**MetadataServiceAccessDetails**](MetadataServiceAccessDetails.md) |  | [optional] 
**runner_labels** | **List[str]** |  | [optional] 
**runner_name** | **str** |  | [optional] 
**runner_registration_url** | **str** | RunnerRegistrationURL is the URL the runner needs to configure itself against. This can be a repository, organization, enterprise (github) or system (gitea) | [optional] 
**runner_tools** | [**RunnerApplicationDownload**](RunnerApplicationDownload.md) |  | [optional] 

## Example

```python
from garm_client.models.instance_metadata import InstanceMetadata

# TODO update the JSON string below
json = "{}"
# create an instance of InstanceMetadata from a JSON string
instance_metadata_instance = InstanceMetadata.from_json(json)
# print the JSON string representation of the object
print(InstanceMetadata.to_json())

# convert the object into a dict
instance_metadata_dict = instance_metadata_instance.to_dict()
# create an instance of InstanceMetadata from a dict
instance_metadata_from_dict = InstanceMetadata.from_dict(instance_metadata_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


