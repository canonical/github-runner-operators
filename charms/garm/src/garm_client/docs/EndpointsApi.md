# garm_client.EndpointsApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**create_gitea_endpoint**](EndpointsApi.md#create_gitea_endpoint) | **POST** /gitea/endpoints | Create a Gitea Endpoint.
[**create_github_endpoint**](EndpointsApi.md#create_github_endpoint) | **POST** /github/endpoints | Create a GitHub Endpoint.
[**delete_gitea_endpoint**](EndpointsApi.md#delete_gitea_endpoint) | **DELETE** /gitea/endpoints/{name} | Delete a Gitea Endpoint.
[**delete_github_endpoint**](EndpointsApi.md#delete_github_endpoint) | **DELETE** /github/endpoints/{name} | Delete a GitHub Endpoint.
[**get_gitea_endpoint**](EndpointsApi.md#get_gitea_endpoint) | **GET** /gitea/endpoints/{name} | Get a Gitea Endpoint.
[**get_github_endpoint**](EndpointsApi.md#get_github_endpoint) | **GET** /github/endpoints/{name} | Get a GitHub Endpoint.
[**list_gitea_endpoints**](EndpointsApi.md#list_gitea_endpoints) | **GET** /gitea/endpoints | List all Gitea Endpoints.
[**list_github_endpoints**](EndpointsApi.md#list_github_endpoints) | **GET** /github/endpoints | List all GitHub Endpoints.
[**update_gitea_endpoint**](EndpointsApi.md#update_gitea_endpoint) | **PUT** /gitea/endpoints/{name} | Update a Gitea Endpoint.
[**update_github_endpoint**](EndpointsApi.md#update_github_endpoint) | **PUT** /github/endpoints/{name} | Update a GitHub Endpoint.


# **create_gitea_endpoint**
> ForgeEndpoint create_gitea_endpoint(body)

Create a Gitea Endpoint.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_gitea_endpoint_params import CreateGiteaEndpointParams
from garm_client.models.forge_endpoint import ForgeEndpoint
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
    api_instance = garm_client.EndpointsApi(api_client)
    body = garm_client.CreateGiteaEndpointParams() # CreateGiteaEndpointParams | Parameters used when creating a Gitea endpoint.

    try:
        # Create a Gitea Endpoint.
        api_response = api_instance.create_gitea_endpoint(body)
        print("The response of EndpointsApi->create_gitea_endpoint:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->create_gitea_endpoint: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**CreateGiteaEndpointParams**](CreateGiteaEndpointParams.md)| Parameters used when creating a Gitea endpoint. | 

### Return type

[**ForgeEndpoint**](ForgeEndpoint.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeEndpoint |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **create_github_endpoint**
> ForgeEndpoint create_github_endpoint(body)

Create a GitHub Endpoint.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_github_endpoint_params import CreateGithubEndpointParams
from garm_client.models.forge_endpoint import ForgeEndpoint
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
    api_instance = garm_client.EndpointsApi(api_client)
    body = garm_client.CreateGithubEndpointParams() # CreateGithubEndpointParams | Parameters used when creating a GitHub endpoint.

    try:
        # Create a GitHub Endpoint.
        api_response = api_instance.create_github_endpoint(body)
        print("The response of EndpointsApi->create_github_endpoint:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->create_github_endpoint: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**CreateGithubEndpointParams**](CreateGithubEndpointParams.md)| Parameters used when creating a GitHub endpoint. | 

### Return type

[**ForgeEndpoint**](ForgeEndpoint.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeEndpoint |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **delete_gitea_endpoint**
> APIErrorResponse delete_gitea_endpoint(name)

Delete a Gitea Endpoint.

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
    api_instance = garm_client.EndpointsApi(api_client)
    name = 'name_example' # str | The name of the Gitea endpoint.

    try:
        # Delete a Gitea Endpoint.
        api_response = api_instance.delete_gitea_endpoint(name)
        print("The response of EndpointsApi->delete_gitea_endpoint:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->delete_gitea_endpoint: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **str**| The name of the Gitea endpoint. | 

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

# **delete_github_endpoint**
> APIErrorResponse delete_github_endpoint(name)

Delete a GitHub Endpoint.

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
    api_instance = garm_client.EndpointsApi(api_client)
    name = 'name_example' # str | The name of the GitHub endpoint.

    try:
        # Delete a GitHub Endpoint.
        api_response = api_instance.delete_github_endpoint(name)
        print("The response of EndpointsApi->delete_github_endpoint:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->delete_github_endpoint: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **str**| The name of the GitHub endpoint. | 

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

# **get_gitea_endpoint**
> ForgeEndpoint get_gitea_endpoint(name)

Get a Gitea Endpoint.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_endpoint import ForgeEndpoint
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
    api_instance = garm_client.EndpointsApi(api_client)
    name = 'name_example' # str | The name of the Gitea endpoint.

    try:
        # Get a Gitea Endpoint.
        api_response = api_instance.get_gitea_endpoint(name)
        print("The response of EndpointsApi->get_gitea_endpoint:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->get_gitea_endpoint: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **str**| The name of the Gitea endpoint. | 

### Return type

[**ForgeEndpoint**](ForgeEndpoint.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeEndpoint |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_github_endpoint**
> ForgeEndpoint get_github_endpoint(name)

Get a GitHub Endpoint.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_endpoint import ForgeEndpoint
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
    api_instance = garm_client.EndpointsApi(api_client)
    name = 'name_example' # str | The name of the GitHub endpoint.

    try:
        # Get a GitHub Endpoint.
        api_response = api_instance.get_github_endpoint(name)
        print("The response of EndpointsApi->get_github_endpoint:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->get_github_endpoint: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **str**| The name of the GitHub endpoint. | 

### Return type

[**ForgeEndpoint**](ForgeEndpoint.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeEndpoint |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_gitea_endpoints**
> List[ForgeEndpoint] list_gitea_endpoints()

List all Gitea Endpoints.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_endpoint import ForgeEndpoint
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
    api_instance = garm_client.EndpointsApi(api_client)

    try:
        # List all Gitea Endpoints.
        api_response = api_instance.list_gitea_endpoints()
        print("The response of EndpointsApi->list_gitea_endpoints:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->list_gitea_endpoints: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**List[ForgeEndpoint]**](ForgeEndpoint.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeEndpoints |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_github_endpoints**
> List[ForgeEndpoint] list_github_endpoints()

List all GitHub Endpoints.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_endpoint import ForgeEndpoint
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
    api_instance = garm_client.EndpointsApi(api_client)

    try:
        # List all GitHub Endpoints.
        api_response = api_instance.list_github_endpoints()
        print("The response of EndpointsApi->list_github_endpoints:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->list_github_endpoints: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**List[ForgeEndpoint]**](ForgeEndpoint.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeEndpoints |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_gitea_endpoint**
> ForgeEndpoint update_gitea_endpoint(name, body)

Update a Gitea Endpoint.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_endpoint import ForgeEndpoint
from garm_client.models.update_gitea_endpoint_params import UpdateGiteaEndpointParams
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
    api_instance = garm_client.EndpointsApi(api_client)
    name = 'name_example' # str | The name of the Gitea endpoint.
    body = garm_client.UpdateGiteaEndpointParams() # UpdateGiteaEndpointParams | Parameters used when updating a Gitea endpoint.

    try:
        # Update a Gitea Endpoint.
        api_response = api_instance.update_gitea_endpoint(name, body)
        print("The response of EndpointsApi->update_gitea_endpoint:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->update_gitea_endpoint: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **str**| The name of the Gitea endpoint. | 
 **body** | [**UpdateGiteaEndpointParams**](UpdateGiteaEndpointParams.md)| Parameters used when updating a Gitea endpoint. | 

### Return type

[**ForgeEndpoint**](ForgeEndpoint.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeEndpoint |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_github_endpoint**
> ForgeEndpoint update_github_endpoint(name, body)

Update a GitHub Endpoint.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_endpoint import ForgeEndpoint
from garm_client.models.update_github_endpoint_params import UpdateGithubEndpointParams
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
    api_instance = garm_client.EndpointsApi(api_client)
    name = 'name_example' # str | The name of the GitHub endpoint.
    body = garm_client.UpdateGithubEndpointParams() # UpdateGithubEndpointParams | Parameters used when updating a GitHub endpoint.

    try:
        # Update a GitHub Endpoint.
        api_response = api_instance.update_github_endpoint(name, body)
        print("The response of EndpointsApi->update_github_endpoint:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EndpointsApi->update_github_endpoint: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **str**| The name of the GitHub endpoint. | 
 **body** | [**UpdateGithubEndpointParams**](UpdateGithubEndpointParams.md)| Parameters used when updating a GitHub endpoint. | 

### Return type

[**ForgeEndpoint**](ForgeEndpoint.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeEndpoint |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

