## Execute the file
1. goes to the root directory
2. python server/main.py to start the server. 
3. python client_dev/main.py if you're a developer.
4. python client_player/main.py if you're a user or player.

* To reset the environment, python reset_env.py
* pip install -r requirements.txt to install the environment (pygame)

## File structure
* client_dev/
    - my_game_sources
    - client.py
    - server.py
* client_player/
    - downloads/ 
    - lobby_client.py
    - main.py
* common/
    - protocol.py
    - utils.py
* server/ 
    - services/
        * auth.py
        * db.py
        * lobby.py
        * store.py
    - storage/
    - main.py 
* requirements.txt 
* reset_env.py 


## IP & PORT
* client_player/lobby_client.py contains IP & PORT
* client_dev/developer_client.py containss IP & PORT
* server/main.py is the main server, lobby and developer will connect to SERVER IP & PORT
* server/services/lobby.py uses s.connect_ex(('localhost', port)) to find PORT and to create game server