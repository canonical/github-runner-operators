# garm_client.ScalesetsApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**create_enterprise_scale_set**](ScalesetsApi.md#create_enterprise_scale_set) | **POST** /enterprises/{enterpriseID}/scalesets | Create enterprise pool with the parameters given.
[**create_org_scale_set**](ScalesetsApi.md#create_org_scale_set) | **POST** /organizations/{orgID}/scalesets | Create organization scale set with the parameters given.
[**create_repo_scale_set**](ScalesetsApi.md#create_repo_scale_set) | **POST** /repositories/{repoID}/scalesets | Create repository scale set with the parameters given.
[**delete_scale_set**](ScalesetsApi.md#delete_scale_set) | **DELETE** /scalesets/{scalesetID} | Delete scale set by ID.
[**get_scale_set**](ScalesetsApi.md#get_scale_set) | **GET** /scalesets/{scalesetID} | Get scale set by ID.
[**list_enterprise_scale_sets**](ScalesetsApi.md#list_enterprise_scale_sets) | **GET** /enterprises/{enterpriseID}/scalesets | List enterprise scale sets.
[**list_org_scale_sets**](ScalesetsApi.md#list_org_scale_sets) | **GET** /organizations/{orgID}/scalesets | List organization scale sets.
[**list_repo_scale_sets**](ScalesetsApi.md#list_repo_scale_sets) | **GET** /repositories/{repoID}/scalesets | List repository scale sets.
[**list_scalesets**](ScalesetsApi.md#list_scalesets) | **GET** /scalesets | List all scalesets.
[**update_scale_set**](ScalesetsApi.md#update_scale_set) | **PUT** /scalesets/{scalesetID} | Update scale set by ID.


# **create_enterprise_scale_set**
> ScaleSet create_enterprise_scale_set(enterprise_id, body)

Create enterprise pool with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_scale_set_params import CreateScaleSetParams
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.ScalesetsApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    body = garm_client.CreateScaleSetParams() # CreateScaleSetParams | Parameters used when creating the enterprise scale set.

    try:
        # Create enterprise pool with the parameters given.
        api_response = api_instance.create_enterprise_scale_set(enterprise_id, body)
        print("The response of ScalesetsApi->create_enterprise_scale_set:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->create_enterprise_scale_set: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 
 **body** | [**CreateScaleSetParams**](CreateScaleSetParams.md)| Parameters used when creating the enterprise scale set. | 

### Return type

[**ScaleSet**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSet |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **create_org_scale_set**
> ScaleSet create_org_scale_set(org_id, body)

Create organization scale set with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_scale_set_params import CreateScaleSetParams
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.ScalesetsApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.
    body = garm_client.CreateScaleSetParams() # CreateScaleSetParams | Parameters used when creating the organization scale set.

    try:
        # Create organization scale set with the parameters given.
        api_response = api_instance.create_org_scale_set(org_id, body)
        print("The response of ScalesetsApi->create_org_scale_set:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->create_org_scale_set: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 
 **body** | [**CreateScaleSetParams**](CreateScaleSetParams.md)| Parameters used when creating the organization scale set. | 

### Return type

[**ScaleSet**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSet |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **create_repo_scale_set**
> ScaleSet create_repo_scale_set(repo_id, body)

Create repository scale set with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_scale_set_params import CreateScaleSetParams
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.ScalesetsApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    body = garm_client.CreateScaleSetParams() # CreateScaleSetParams | Parameters used when creating the repository scale set.

    try:
        # Create repository scale set with the parameters given.
        api_response = api_instance.create_repo_scale_set(repo_id, body)
        print("The response of ScalesetsApi->create_repo_scale_set:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->create_repo_scale_set: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 
 **body** | [**CreateScaleSetParams**](CreateScaleSetParams.md)| Parameters used when creating the repository scale set. | 

### Return type

[**ScaleSet**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSet |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **delete_scale_set**
> APIErrorResponse delete_scale_set(scaleset_id)

Delete scale set by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.api_error_response import APIErrorResponse
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
    api_instance = garm_client.ScalesetsApi(api_client)
    scaleset_id = 'scaleset_id_example' # str | ID of the scale set to delete.

    try:
        # Delete scale set by ID.
        api_response = api_instance.delete_scale_set(scaleset_id)
        print("The response of ScalesetsApi->delete_scale_set:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->delete_scale_set: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **scaleset_id** | **str**| ID of the scale set to delete. | 

### Return type

[**APIErrorResponse**](APIErrorResponse.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_scale_set**
> ScaleSet get_scale_set(scaleset_id)

Get scale set by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.ScalesetsApi(api_client)
    scaleset_id = 'scaleset_id_example' # str | ID of the scale set to fetch.

    try:
        # Get scale set by ID.
        api_response = api_instance.get_scale_set(scaleset_id)
        print("The response of ScalesetsApi->get_scale_set:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->get_scale_set: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **scaleset_id** | **str**| ID of the scale set to fetch. | 

### Return type

[**ScaleSet**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSet |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_enterprise_scale_sets**
> List[ScaleSet] list_enterprise_scale_sets(enterprise_id)

List enterprise scale sets.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.ScalesetsApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.

    try:
        # List enterprise scale sets.
        api_response = api_instance.list_enterprise_scale_sets(enterprise_id)
        print("The response of ScalesetsApi->list_enterprise_scale_sets:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->list_enterprise_scale_sets: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 

### Return type

[**List[ScaleSet]**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSets |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_org_scale_sets**
> List[ScaleSet] list_org_scale_sets(org_id)

List organization scale sets.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.ScalesetsApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.

    try:
        # List organization scale sets.
        api_response = api_instance.list_org_scale_sets(org_id)
        print("The response of ScalesetsApi->list_org_scale_sets:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->list_org_scale_sets: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 

### Return type

[**List[ScaleSet]**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSets |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_repo_scale_sets**
> List[ScaleSet] list_repo_scale_sets(repo_id)

List repository scale sets.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.ScalesetsApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # List repository scale sets.
        api_response = api_instance.list_repo_scale_sets(repo_id)
        print("The response of ScalesetsApi->list_repo_scale_sets:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->list_repo_scale_sets: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 

### Return type

[**List[ScaleSet]**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSets |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_scalesets**
> List[ScaleSet] list_scalesets()

List all scalesets.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.ScalesetsApi(api_client)

    try:
        # List all scalesets.
        api_response = api_instance.list_scalesets()
        print("The response of ScalesetsApi->list_scalesets:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->list_scalesets: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**List[ScaleSet]**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSets |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_scale_set**
> ScaleSet update_scale_set(scaleset_id, body)

Update scale set by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.scale_set import ScaleSet
from garm_client.models.update_scale_set_params import UpdateScaleSetParams
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
    api_instance = garm_client.ScalesetsApi(api_client)
    scaleset_id = 'scaleset_id_example' # str | ID of the scale set to update.
    body = garm_client.UpdateScaleSetParams() # UpdateScaleSetParams | Parameters to update the scale set with.

    try:
        # Update scale set by ID.
        api_response = api_instance.update_scale_set(scaleset_id, body)
        print("The response of ScalesetsApi->update_scale_set:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ScalesetsApi->update_scale_set: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **scaleset_id** | **str**| ID of the scale set to update. | 
 **body** | [**UpdateScaleSetParams**](UpdateScaleSetParams.md)| Parameters to update the scale set with. | 

### Return type

[**ScaleSet**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSet |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

