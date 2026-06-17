# garm_client.ProvidersApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**list_providers**](ProvidersApi.md#list_providers) | **GET** /providers | List all providers.


# **list_providers**
> List[Provider] list_providers()

List all providers.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.provider import Provider
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.ProvidersApi(api_client)

    try:
        # List all providers.
        api_response = api_instance.list_providers()
        print("The response of ProvidersApi->list_providers:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ProvidersApi->list_providers: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**List[Provider]**](Provider.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Providers |  -  |
**400** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

