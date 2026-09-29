# garm_client.ForgeInstancesApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**create_forge_instance**](ForgeInstancesApi.md#create_forge_instance) | **POST** /forge-instances | Create forge instance with the given parameters.
[**create_forge_instance_pool**](ForgeInstancesApi.md#create_forge_instance_pool) | **POST** /forge-instances/{forgeInstanceID}/pools | Create forge instance pool with the parameters given.
[**delete_forge_instance**](ForgeInstancesApi.md#delete_forge_instance) | **DELETE** /forge-instances/{forgeInstanceID} | Delete forge instance by ID.
[**delete_forge_instance_pool**](ForgeInstancesApi.md#delete_forge_instance_pool) | **DELETE** /forge-instances/{forgeInstanceID}/pools/{poolID} | Delete forge instance pool by ID.
[**get_forge_instance**](ForgeInstancesApi.md#get_forge_instance) | **GET** /forge-instances/{forgeInstanceID} | Get forge instance by ID.
[**get_forge_instance_pool**](ForgeInstancesApi.md#get_forge_instance_pool) | **GET** /forge-instances/{forgeInstanceID}/pools/{poolID} | Get forge instance pool by ID.
[**get_forge_instance_webhook_info**](ForgeInstancesApi.md#get_forge_instance_webhook_info) | **GET** /forge-instances/{forgeInstanceID}/webhook | Get information about the GARM installed webhook on a forge instance.
[**install_forge_instance_webhook**](ForgeInstancesApi.md#install_forge_instance_webhook) | **POST** /forge-instances/{forgeInstanceID}/webhook | 
[**list_forge_instance_instances**](ForgeInstancesApi.md#list_forge_instance_instances) | **GET** /forge-instances/{forgeInstanceID}/instances | List forge instance runner instances.
[**list_forge_instance_pools**](ForgeInstancesApi.md#list_forge_instance_pools) | **GET** /forge-instances/{forgeInstanceID}/pools | List forge instance pools.
[**list_forge_instances**](ForgeInstancesApi.md#list_forge_instances) | **GET** /forge-instances | List all forge instances.
[**uninstall_forge_instance_webhook**](ForgeInstancesApi.md#uninstall_forge_instance_webhook) | **DELETE** /forge-instances/{forgeInstanceID}/webhook | Uninstall forge instance webhook.
[**update_forge_instance**](ForgeInstancesApi.md#update_forge_instance) | **PUT** /forge-instances/{forgeInstanceID} | Update forge instance with the given parameters.
[**update_forge_instance_pool**](ForgeInstancesApi.md#update_forge_instance_pool) | **PUT** /forge-instances/{forgeInstanceID}/pools/{poolID} | Update forge instance pool with the parameters given.


# **create_forge_instance**
> ForgeInstance create_forge_instance(body)

Create forge instance with the given parameters.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_forge_instance_params import CreateForgeInstanceParams
from garm_client.models.forge_instance import ForgeInstance
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    body = garm_client.CreateForgeInstanceParams() # CreateForgeInstanceParams | Parameters used to create the forge instance.

    try:
        # Create forge instance with the given parameters.
        api_response = api_instance.create_forge_instance(body)
        print("The response of ForgeInstancesApi->create_forge_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->create_forge_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**CreateForgeInstanceParams**](CreateForgeInstanceParams.md)| Parameters used to create the forge instance. | 

### Return type

[**ForgeInstance**](ForgeInstance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeInstance |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **create_forge_instance_pool**
> Pool create_forge_instance_pool(forge_instance_id, body)

Create forge instance pool with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_pool_params import CreatePoolParams
from garm_client.models.pool import Pool
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | Forge instance ID.
    body = garm_client.CreatePoolParams() # CreatePoolParams | Parameters used when creating the forge instance pool.

    try:
        # Create forge instance pool with the parameters given.
        api_response = api_instance.create_forge_instance_pool(forge_instance_id, body)
        print("The response of ForgeInstancesApi->create_forge_instance_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->create_forge_instance_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| Forge instance ID. | 
 **body** | [**CreatePoolParams**](CreatePoolParams.md)| Parameters used when creating the forge instance pool. | 

### Return type

[**Pool**](Pool.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Pool |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **delete_forge_instance**
> APIErrorResponse delete_forge_instance(forge_instance_id, keep_webhook=keep_webhook)

Delete forge instance by ID.

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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | ID of the forge instance to delete.
    keep_webhook = True # bool | If true and a webhook is installed for this forge instance, it will not be removed. (optional)

    try:
        # Delete forge instance by ID.
        api_response = api_instance.delete_forge_instance(forge_instance_id, keep_webhook=keep_webhook)
        print("The response of ForgeInstancesApi->delete_forge_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->delete_forge_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| ID of the forge instance to delete. | 
 **keep_webhook** | **bool**| If true and a webhook is installed for this forge instance, it will not be removed. | [optional] 

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

# **delete_forge_instance_pool**
> APIErrorResponse delete_forge_instance_pool(forge_instance_id, pool_id)

Delete forge instance pool by ID.

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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | Forge instance ID.
    pool_id = 'pool_id_example' # str | ID of the forge instance pool to delete.

    try:
        # Delete forge instance pool by ID.
        api_response = api_instance.delete_forge_instance_pool(forge_instance_id, pool_id)
        print("The response of ForgeInstancesApi->delete_forge_instance_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->delete_forge_instance_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| Forge instance ID. | 
 **pool_id** | **str**| ID of the forge instance pool to delete. | 

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

# **get_forge_instance**
> ForgeInstance get_forge_instance(forge_instance_id)

Get forge instance by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_instance import ForgeInstance
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | The ID of the forge instance to fetch.

    try:
        # Get forge instance by ID.
        api_response = api_instance.get_forge_instance(forge_instance_id)
        print("The response of ForgeInstancesApi->get_forge_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->get_forge_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| The ID of the forge instance to fetch. | 

### Return type

[**ForgeInstance**](ForgeInstance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeInstance |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_forge_instance_pool**
> Pool get_forge_instance_pool(forge_instance_id, pool_id)

Get forge instance pool by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.pool import Pool
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | Forge instance ID.
    pool_id = 'pool_id_example' # str | Pool ID.

    try:
        # Get forge instance pool by ID.
        api_response = api_instance.get_forge_instance_pool(forge_instance_id, pool_id)
        print("The response of ForgeInstancesApi->get_forge_instance_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->get_forge_instance_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| Forge instance ID. | 
 **pool_id** | **str**| Pool ID. | 

### Return type

[**Pool**](Pool.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Pool |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_forge_instance_webhook_info**
> HookInfo get_forge_instance_webhook_info(forge_instance_id)

Get information about the GARM installed webhook on a forge instance.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.hook_info import HookInfo
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | Forge instance ID.

    try:
        # Get information about the GARM installed webhook on a forge instance.
        api_response = api_instance.get_forge_instance_webhook_info(forge_instance_id)
        print("The response of ForgeInstancesApi->get_forge_instance_webhook_info:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->get_forge_instance_webhook_info: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| Forge instance ID. | 

### Return type

[**HookInfo**](HookInfo.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | HookInfo |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **install_forge_instance_webhook**
> HookInfo install_forge_instance_webhook(forge_instance_id, body)

Install the GARM webhook for a forge instance. The secret configured on the forge instance will
be used to validate the requests.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.hook_info import HookInfo
from garm_client.models.install_webhook_params import InstallWebhookParams
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | Forge instance ID.
    body = garm_client.InstallWebhookParams() # InstallWebhookParams | Parameters used when creating the forge instance webhook.

    try:
        api_response = api_instance.install_forge_instance_webhook(forge_instance_id, body)
        print("The response of ForgeInstancesApi->install_forge_instance_webhook:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->install_forge_instance_webhook: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| Forge instance ID. | 
 **body** | [**InstallWebhookParams**](InstallWebhookParams.md)| Parameters used when creating the forge instance webhook. | 

### Return type

[**HookInfo**](HookInfo.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | HookInfo |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_forge_instance_instances**
> List[Instance] list_forge_instance_instances(forge_instance_id)

List forge instance runner instances.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.instance import Instance
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | Forge instance ID.

    try:
        # List forge instance runner instances.
        api_response = api_instance.list_forge_instance_instances(forge_instance_id)
        print("The response of ForgeInstancesApi->list_forge_instance_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->list_forge_instance_instances: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| Forge instance ID. | 

### Return type

[**List[Instance]**](Instance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Instances |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_forge_instance_pools**
> List[Pool] list_forge_instance_pools(forge_instance_id)

List forge instance pools.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.pool import Pool
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | Forge instance ID.

    try:
        # List forge instance pools.
        api_response = api_instance.list_forge_instance_pools(forge_instance_id)
        print("The response of ForgeInstancesApi->list_forge_instance_pools:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->list_forge_instance_pools: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| Forge instance ID. | 

### Return type

[**List[Pool]**](Pool.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Pools |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_forge_instances**
> List[ForgeInstance] list_forge_instances(endpoint=endpoint)

List all forge instances.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_instance import ForgeInstance
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    endpoint = 'endpoint_example' # str | Exact endpoint name to filter by (optional)

    try:
        # List all forge instances.
        api_response = api_instance.list_forge_instances(endpoint=endpoint)
        print("The response of ForgeInstancesApi->list_forge_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->list_forge_instances: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **endpoint** | **str**| Exact endpoint name to filter by | [optional] 

### Return type

[**List[ForgeInstance]**](ForgeInstance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeInstances |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **uninstall_forge_instance_webhook**
> APIErrorResponse uninstall_forge_instance_webhook(forge_instance_id)

Uninstall forge instance webhook.

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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | Forge instance ID.

    try:
        # Uninstall forge instance webhook.
        api_response = api_instance.uninstall_forge_instance_webhook(forge_instance_id)
        print("The response of ForgeInstancesApi->uninstall_forge_instance_webhook:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->uninstall_forge_instance_webhook: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| Forge instance ID. | 

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

# **update_forge_instance**
> ForgeInstance update_forge_instance(forge_instance_id, body)

Update forge instance with the given parameters.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.forge_instance import ForgeInstance
from garm_client.models.update_entity_params import UpdateEntityParams
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | The ID of the forge instance to update.
    body = garm_client.UpdateEntityParams() # UpdateEntityParams | Parameters used when updating the forge instance.

    try:
        # Update forge instance with the given parameters.
        api_response = api_instance.update_forge_instance(forge_instance_id, body)
        print("The response of ForgeInstancesApi->update_forge_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->update_forge_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| The ID of the forge instance to update. | 
 **body** | [**UpdateEntityParams**](UpdateEntityParams.md)| Parameters used when updating the forge instance. | 

### Return type

[**ForgeInstance**](ForgeInstance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ForgeInstance |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_forge_instance_pool**
> Pool update_forge_instance_pool(forge_instance_id, pool_id, body)

Update forge instance pool with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.pool import Pool
from garm_client.models.update_pool_params import UpdatePoolParams
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
    api_instance = garm_client.ForgeInstancesApi(api_client)
    forge_instance_id = 'forge_instance_id_example' # str | Forge instance ID.
    pool_id = 'pool_id_example' # str | ID of the forge instance pool to update.
    body = garm_client.UpdatePoolParams() # UpdatePoolParams | Parameters used when updating the forge instance pool.

    try:
        # Update forge instance pool with the parameters given.
        api_response = api_instance.update_forge_instance_pool(forge_instance_id, pool_id, body)
        print("The response of ForgeInstancesApi->update_forge_instance_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ForgeInstancesApi->update_forge_instance_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **forge_instance_id** | **str**| Forge instance ID. | 
 **pool_id** | **str**| ID of the forge instance pool to update. | 
 **body** | [**UpdatePoolParams**](UpdatePoolParams.md)| Parameters used when updating the forge instance pool. | 

### Return type

[**Pool**](Pool.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Pool |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

