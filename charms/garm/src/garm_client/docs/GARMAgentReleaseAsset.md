# GARMAgentReleaseAsset

GARMAgentReleaseAsset describes one downloadable binary of a garm-agent release.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**digest** | **str** | Digest is the checksum of the asset as declared upstream (typically \&quot;sha256:&lt;hex&gt;\&quot;). | [optional] 
**download_url** | **str** | DownloadURL is the upstream URL the asset can be downloaded from. | [optional] 
**name** | **str** | Name is the file name of the asset. | [optional] 
**size** | **int** | Size is the size of the asset in bytes. | [optional] 

## Example

```python
from garm_client.models.garm_agent_release_asset import GARMAgentReleaseAsset

# TODO update the JSON string below
json = "{}"
# create an instance of GARMAgentReleaseAsset from a JSON string
garm_agent_release_asset_instance = GARMAgentReleaseAsset.from_json(json)
# print the JSON string representation of the object
print(GARMAgentReleaseAsset.to_json())

# convert the object into a dict
garm_agent_release_asset_dict = garm_agent_release_asset_instance.to_dict()
# create an instance of GARMAgentReleaseAsset from a dict
garm_agent_release_asset_from_dict = GARMAgentReleaseAsset.from_dict(garm_agent_release_asset_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


