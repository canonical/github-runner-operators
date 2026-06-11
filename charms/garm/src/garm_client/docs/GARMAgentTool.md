# GARMAgentTool


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**created_at** | **datetime** |  | [optional] 
**description** | **str** |  | [optional] 
**download_url** | **str** |  | [optional] 
**file_type** | **str** |  | [optional] 
**id** | **int** |  | [optional] 
**name** | **str** |  | [optional] 
**origin** | **str** | Origin defines where the GARM agent tool originated from. When manually uploaded, this field is set to \&quot;manual\&quot;. When synced from a release URL, this will hold the release URL where the tools originated from. | [optional] 
**os_arch** | **str** |  | [optional] 
**os_type** | **str** |  | [optional] 
**sha256sum** | **str** |  | [optional] 
**size** | **int** |  | [optional] 
**source** | **str** | Source indicates where this tool is currently stored. \&quot;local\&quot; means the tool is stored in the internal object store. \&quot;upstream\&quot; means the tool is only available from the upstream cached release and has not been downloaded locally. | [optional] 
**updated_at** | **datetime** |  | [optional] 
**version** | **str** |  | [optional] 

## Example

```python
from garm_client.models.garm_agent_tool import GARMAgentTool

# TODO update the JSON string below
json = "{}"
# create an instance of GARMAgentTool from a JSON string
garm_agent_tool_instance = GARMAgentTool.from_json(json)
# print the JSON string representation of the object
print(GARMAgentTool.to_json())

# convert the object into a dict
garm_agent_tool_dict = garm_agent_tool_instance.to_dict()
# create an instance of GARMAgentTool from a dict
garm_agent_tool_from_dict = GARMAgentTool.from_dict(garm_agent_tool_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


