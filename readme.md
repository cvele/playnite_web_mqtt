# Playnite Web MQTT Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

> ⚠️ **Warning**: This project is still in development. Use at your own risk!

This custom Home Assistant integration allows you to monitor and control your Playnite games via MQTT. It creates game-related entities (such as switches and buttons) to start, stop, install, and uninstall games, as well as retrieve cover images and game library data from Playnite.

## Features

- **Game Discovery**: Automatically create switches for games discovered via Playnite's MQTT topics.
- **Game Control**: Control games by turning them on/off (starting/stopping games) and manage game installations (install/uninstall buttons not yet implemented).
- **Cover Images**: Automatically receive and display cover images for your games.
- **Request Game Library**: Request the game library update from Playnite using a button entity.
- **MQTT-based Communication**: Communicate with Playnite using MQTT to get updates about game states and covers.

## Installation

### Prerequisites
- Playnite with the **PlayniteWeb** plugin configured. @alex-codes
- An MQTT broker set up in Home Assistant (like the [Mosquitto Broker Add-on](https://www.home-assistant.io/addons/mosquitto/)).

### Manual Installation
1. Copy the `playnite_web_mqtt` directory to your `custom_components` folder in Home Assistant.
   - If you do not have this folder, create it at `<config_dir>/custom_components/playnite_web_mqtt`.
2. Restart Home Assistant.
3. Add and configure the integration via Home Assistant's **Configuration** > **Devices & Services** page.

### HACS Installation
1. Open the HACS panel in Home Assistant.
2. Go to **Integrations** and click on the three dots in the upper-right corner.
3. Select **Custom repositories** and add the GitHub repository URL of this integration.
4. Search for **Playnite Web MQTT**, and click **Install**.
5. Restart Home Assistant and configure the integration via the UI.

## Configuration

You can configure the integration via Home Assistant's UI by following these steps:
1. Go to **Configuration** > **Devices & Services**.
2. Click **Add Integration** and search for **Playnite Web MQTT**.
3. Fill in the necessary MQTT connection details:
   - MQTT Broker
   - MQTT Port
   - (Optional) Username and Password
   - Topic Base: Set to the same topic base as configured in Playnite's MQTT Web plugin.

The integration will subscribe to Playnite's MQTT topics, creating game switches and retrieving cover images.

### Configuration Options

- **MQTT Broker**: The address of your MQTT broker.
- **MQTT Port**: The port for your MQTT broker (default is `1883`).
- **MQTT Username/Password**: (Optional) Credentials for your MQTT broker.
- **Topic Base**: The MQTT topic base, typically something like `playnite/playniteweb_<your-pc-name>`.

## Supported Entities

- **Switch Entities**:
  - Each game discovered via Playnite is represented as a switch. Turning the switch on starts the game, and turning it off stops the game.
- **Button Entities**:
  - A button to request the game library from Playnite.

## Example MQTT Topic Structure

The integration listens to Playnite MQTT topics structured as follows:

- `playnite/playniteweb_<your-pc-name>/entity/release/<game-id>/state`: Game state (started, stopped).
- `playnite/playniteweb_<your-pc-name>/entity/release/<game-id>/asset/cover`: Game cover image.
- `playnite/playniteweb_<your-pc-name>/response/game/state`: General game state response.

## Troubleshooting

- Ensure your MQTT broker is configured and accessible by both Playnite and Home Assistant.
- Verify that the MQTT topics match the `topic_base` configured in the Playnite Web plugin.

## Known Issues

- State of the switch is not reliable. This is being worked on.
- Some games will not stop when switch is turned off, again being worked on.

## License

This project is licensed under the MIT License.

## Contributions

Feel free to open issues or contribute to this repository via pull requests.
