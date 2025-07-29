# FFG Fuel Price List
## Project Description
A tiny webpage to display the fuel prices at airports around Braunschweig. Helps FFG Pilots to fuel their aircrafts at little cost.

## Technical Description
Python script for querying the fuel prices from [spritpreisliste.de](https://spritpreisliste.de) for relevant FFG airports, and rendering as HTML page. Hosted as Microsoft Azure Functions App.

## Development
Prepare the development environment ([reference](https://learn.microsoft.com/en-us/azure/azure-functions/how-to-create-function-azure-cli?pivots=programming-language-python&tabs=macos%2Cbash%2Cazure-cli)):
```
brew install azure-functions-core-tools@4
```
Go to `src` folder and activate the python env:
````
source .venv/bin/activate
````
Start the function host:
````
func start
````
## Deployment
Ensure you're logged in to Azure CLI:
```
az login --use-device-code
````
Start the deployment:
````
func azure functionapp publish ffg-fuelprices
````
