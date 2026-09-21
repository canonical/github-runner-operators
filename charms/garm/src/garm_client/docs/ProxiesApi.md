# garm_client.ProxiesApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**create_proxy**](ProxiesApi.md#create_proxy) | **POST** /proxies | Create proxy with the parameters given.
[**delete_proxy**](ProxiesApi.md#delete_proxy) | **DELETE** /proxies/{proxyID} | Delete proxy by ID.
[**get_proxy**](ProxiesApi.md#get_proxy) | **GET** /proxies/{proxyID} | Get proxy by ID.
[**list_proxies**](ProxiesApi.md#list_proxies) | **GET** /proxies | List proxies.
[**update_proxy**](ProxiesApi.md#update_proxy) | **PUT** /proxies/{proxyID} | Update proxy with the parameters given.


# **create_proxy**
> Proxy create_proxy(body)

Create proxy with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_proxy_params import CreateProxyParams
from garm_client.models.proxy import Proxy
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
    api_instance = garm_client.ProxiesApi(api_client)
    body = garm_client.CreateProxyParams() # CreateProxyParams | Parameters used when creating the proxy.

    try:
        # Create proxy with the parameters given.
        api_response = api_instance.create_proxy(body)
        print("The response of ProxiesApi->create_proxy:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ProxiesApi->create_proxy: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**CreateProxyParams**](CreateProxyParams.md)| Parameters used when creating the proxy. | 

### Return type

[**Proxy**](Proxy.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Proxy |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **delete_proxy**
> APIErrorResponse delete_proxy(proxy_id)

Delete proxy by ID.

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
    api_instance = garm_client.ProxiesApi(api_client)
    proxy_id = 3.4 # float | ID of the proxy to delete.

    try:
        # Delete proxy by ID.
        api_response = api_instance.delete_proxy(proxy_id)
        print("The response of ProxiesApi->delete_proxy:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ProxiesApi->delete_proxy: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **proxy_id** | **float**| ID of the proxy to delete. | 

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

# **get_proxy**
> Proxy get_proxy(proxy_id)

Get proxy by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.proxy import Proxy
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
    api_instance = garm_client.ProxiesApi(api_client)
    proxy_id = 3.4 # float | ID of the proxy to fetch.

    try:
        # Get proxy by ID.
        api_response = api_instance.get_proxy(proxy_id)
        print("The response of ProxiesApi->get_proxy:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ProxiesApi->get_proxy: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **proxy_id** | **float**| ID of the proxy to fetch. | 

### Return type

[**Proxy**](Proxy.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Proxy |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_proxies**
> List[Proxy] list_proxies()

List proxies.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.proxy import Proxy
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
    api_instance = garm_client.ProxiesApi(api_client)

    try:
        # List proxies.
        api_response = api_instance.list_proxies()
        print("The response of ProxiesApi->list_proxies:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ProxiesApi->list_proxies: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**List[Proxy]**](Proxy.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Proxies |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_proxy**
> Proxy update_proxy(proxy_id, body)

Update proxy with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.proxy import Proxy
from garm_client.models.update_proxy_params import UpdateProxyParams
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
    api_instance = garm_client.ProxiesApi(api_client)
    proxy_id = 3.4 # float | ID of the proxy to update.
    body = garm_client.UpdateProxyParams() # UpdateProxyParams | Parameters used when updating the proxy.

    try:
        # Update proxy with the parameters given.
        api_response = api_instance.update_proxy(proxy_id, body)
        print("The response of ProxiesApi->update_proxy:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ProxiesApi->update_proxy: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **proxy_id** | **float**| ID of the proxy to update. | 
 **body** | [**UpdateProxyParams**](UpdateProxyParams.md)| Parameters used when updating the proxy. | 

### Return type

[**Proxy**](Proxy.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Proxy |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

