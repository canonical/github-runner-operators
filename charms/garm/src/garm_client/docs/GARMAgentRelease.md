# GARMAgentRelease

GARMAgentRelease describes one garm-agent release available at the controller's releases URL, as recorded in the cached release index.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**assets** | [**List[GARMAgentReleaseAsset]**](GARMAgentReleaseAsset.md) | Assets lists the downloadable binaries the release ships. Checksum files are omitted; the digest of each asset is included instead. | [optional] 
**latest** | **bool** | Latest indicates this is the release \&quot;latest\&quot; currently resolves to. | [optional] 
**os_archs** | **List[str]** | OSArchs lists the \&quot;os_type/os_arch\&quot; combinations the release ships agent binaries for. | [optional] 
**pinned** | **bool** | Pinned indicates this is the version the controller is pinned to. | [optional] 
**prerelease** | **bool** | Prerelease indicates the release is marked as a pre-release upstream. | [optional] 
**release_notes** | **str** | ReleaseNotes holds the release description as published upstream (typically markdown), so operators can see what changed in a release before pinning to it. | [optional] 
**version** | **str** | Version is the release tag. | [optional] 

## Example

```python
from garm_client.models.garm_agent_release import GARMAgentRelease

# TODO update the JSON string below
json = "{}"
# create an instance of GARMAgentRelease from a JSON string
garm_agent_release_instance = GARMAgentRelease.from_json(json)
# print the JSON string representation of the object
print(GARMAgentRelease.to_json())

# convert the object into a dict
garm_agent_release_dict = garm_agent_release_instance.to_dict()
# create an instance of GARMAgentRelease from a dict
garm_agent_release_from_dict = GARMAgentRelease.from_dict(garm_agent_release_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


