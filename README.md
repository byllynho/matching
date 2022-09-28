<div id="top"></div>

<h3 align="center">Guess Who</h3>

  <p align="center">
    Guess Who backend repository
  </p>
</div>

<!-- ABOUT THE PROJECT -->
## About The Project

Guess Who is an application that consist of several RestAPIs that are used during the process of matching cases to studies as well as a data interface for the information generated during the process of matching.

### Built With

* [FastAPI](https://fastapi.tiangolo.com/)
* [Alembic](https://alembic.sqlalchemy.org/en/latest/)
* [SQLAlchemy](https://www.sqlalchemy.org/)
* [Celery](https://docs.celeryq.dev/en/stable/getting-started/introduction.html)
* [RabbitMQ](https://www.rabbitmq.com/)
* [Docker](https://www.docker.com/)
* [Kafka](https://kafka.apache.org/)
* [NGINX](https://www.nginx.com/)

<!-- GETTING STARTED -->
## Getting Started

To get a local copy up and running follow these simple example steps.

### Prerequisites

This project uses containers on its deployment as well as during development. We use docker-compose to create environment.

* Docker
* Docker compose

For interaction with the database, we suggest the use of DBeaver:

* [DBeaver](https://dbeaver.io/)
SET THE ARGS ON COMPOSE FILE (worker, guess-who):
- **SEGAWAY_BUILD_USERNAME**: Gitlab username used to download the Visionaire package
- **SEGAWAY_BUILD_TOKEN**: Gitlab build token used to download the Visionaire package

SET THE ENVIRONMENT VARIABLES ON THE COMPOSE FILE:
- **DATABASE_URL**: URL to the postgress database (Default: postgresql://postgres:password@postgres:5432/postgres)
- **PROJECT_NAME**: Name of the project (Default: visionaire-web-dev)
- **SEGAWAY_BROKER_URL**: RabbitMQ/Broker url for communication (Default: amqp://guest:guest@message-broker:5672)
- **SEGAWAY_KAFKA_URL**: URL for the Kafka broker (Default: broker:29092)
- **SEGAWAY_KAFKA_PERFECT_MATCH**: (Default: perfect_match)
- **SEGAWAY_KAFKA_INSTANCE_TOPIC**: (Default: orthanc-index)
- **SONADOR_URL**: (Default: http://imaging.visdev.smith-nephew.com)
- **SONADOR_INTERNAL_DNS**: (Default: 'False')
- **ALLOWED_ORIGINS**: CORS that allowed to communicate to server (Default: 'http://localhost,http://localhost:3000')
- **AUTH_URL**: (Default: https://auth.visdev.smith-nephew.com)
- **SONADOR_IMAGING_SERVER**: Sonador server used during the process of matching
- **SONADOR_APITOKEN**: Sonador API Token used to authenticate to sonador
- **VCM_USER**: Username used to retrieve data from VCM for the matching
- **VCM_PASSWORD**: Password for the user used to retrieve data from VCM for the matching
- **JWT_KEY**: Encryption key used to encrypt the JWT token (Look at FusionAuth documentation)
- **JWT_AUDIENCE**: OAuth server audience token (Look at FusionAuth documentation)
- **AUTH_API_KEY**: FusionAuth API key used to communicate with the server RestAPIs
- **URL_WEBSOCKET**: URL to application websocket endpoint (ws://guess-who:8888)
- **GUESS_WHO_CLEAN_TIMER**: Time, in minutes, in which the process of cleaning running Guess Who process should occur
- **PROCESSING_MATCHES_TIME_CHECK**: Define the stream timer for the Server-side event stream to publish the list of processeing matches

(Guess Who algorithm variables)
- **TRANSFORM_PHONETIC**: (Optional: True) Defines if we transform the words/features during comparisson to its Phonetic form
- **PHONETIC_ALGORITHM**: (Optional: double_metaphone) Define the phonetic algorithm used
- **STEMMING**: (Optional: False) Define if stemming of the world should or should not occurr during the process
- **STRING_COMPARRISON_METHOD**: (Optional: damerau_levenshtein) Define which algorithm is used during the proximity check.

### Installation

1. Clone the repo
   ```sh
   git clone http://gitlab.visdev.smith-nephew.com/medical-imaging/visionaire-web/guess-who.git
   ```
2. Change environment variables on docker-compose-guess-who.yml file, as referenced on the section above.
3. Build containers and migrate database
   ```sh
   ./scripts/build.sh
   ```

<!-- USAGE EXAMPLES -->
## Usage

Once all the containers are up and running correctly, you can navigate to [localhost:8000/api/docs](https://localhost:8000/api/docs). You should see the Swagger interface for interacting with the RestAPIs

_For more examples, please refer to folder DOCS within the repo

## Folder Structure

A quick explanation of the important folders that can be found in this project:
- **app**: Main folder for development. All the important code will be in here
- **nginx**: Folder that contains the server configuration
- **scripts**: Folder that contains script files that facilitate deployment
- **app/api**: Here we have the code for the Rest Endpoints.
- **app/core**: Folder that contains the core functionalaties of an app (authentication, db management, configuration, etc)
- **app/db**: Folder that contains the database model as well as code that interacts directly with the database (CRUD)
- **app/tests**: Folder that contains unit tests
- **app/alembic**: Folder that contains the database migration files.
