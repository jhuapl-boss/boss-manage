# AWS Lambda Layers

[AWS Lambda Layers](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html) allow for including addition code and content in the Lambda environment before the Lambda handler is executed. Layers can be used to include libraries, custom runtimes, or other dependencies without having to package them in the Lambda code zip for the Lambda function.

*Note: The total unzipped size of the Lambda function and all layers cannot exceed 250 MB*

## Lambda Build Support

The new Lambda build process supports creating custom Lambda Layers and using them.

To create a custom Lambda Layer:
* Create a new folder under `cloud_formation/lambda/`
* Copy `cloud_formation/lambda/template.yml` as `lambda.yml` in the new folder from the previous step
* Update the `lambda.yml` and set `is_layer` to `True`
* Update the `lambda.yml` to included the needed instruction for building the layer zip file
  - See [Including Library Dependencies in a Layer](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html#configuration-layers-path) for information on how to package libraries as a layer

To use a custom Lambda Layer:
* Update the `lambda.yml` file for the Lambda that will use the layer and add the new directory name (containing the Layer's `lambda.yml`) to the list of layers
* Rebuild the Lambda, which will automatically build the layer code
