//============================================================================
// Name        : spoc2.cpp
// Author      : kincho
// Version     :
// Copyright   :
// Description : Hello World in C++, Ansi-style
//============================================================================

#include "Console.h"
#include "Login.h"
#include "Chain.cpp"

using namespace std;

int main(int argc, char **argv)
{
	//Parse Login Page
	Login login;
	if (argc <= 1)
		login = Login("data/master.login");

	else
		login = Login(argv[1]);

	//Activate console for client
	Console::Instance().start();

    //Display Login Page
	Console::display(login.getDescription());

    //Get Player login information, make it lowercase for consistency (TODO security).
	string playerName = Console::Instance().prompt();
	for (int k = 0; k < playerName.size(); ++k)
		playerName[k] = tolower(playerName[k]);

	Chain::Instance().request("login " + playerName);

	//TODO Based on Response from Chain, either:
	//		1) Log player in to world
	//		2) If player doesn't exist, allow player to create a new character

	Mob& player = Chain::Instance().getMob(Chain::Instance().getCurrentPlayer());

	//Clear the screen
	Console::Instance().clear_screen();

	//Get what's around player via look command
	Chain::Instance().request(Chain::Instance().getCurrentPlayer(), "look");

	//TODO maybe need to look into another way to do this, via configuration available from Player class that will feed
	//into lookingGlass.
	map<string, int> prompt;
	prompt.insert(make_pair("HP", player.getStat("hp").getCurrent()));
	prompt.insert(make_pair("MP", player.getStat("mp").getCurrent()));

	//HALLOWED GAME LOOPZ
	while (Console::Instance().isActive())
	{
		Chain::Instance().request(player.getDescriptor(), Console::Instance().prompt(prompt));
	}

	return 0;
}
