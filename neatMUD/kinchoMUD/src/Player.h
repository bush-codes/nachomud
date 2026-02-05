/*
 * Player.cpp
 *
 *  Created on: Oct 4, 2009
 *      Author: kincho
 */

#ifndef PLAYER_H
#define PLAYER_H

#include "BrainFactory.cpp"

#include <iostream>
#include <cstdlib>
#include <string>

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

#include "Direction.cpp"
#include "Action.cpp"  //Where is this used currently?  Might be useful for action list validation when we have the time tho.
#include "Stat.h"

using namespace std;
using namespace rapidxml;

class Player
{
	friend class Chain;
	private:
		bool player;
		int mfd; //player family descriptor
		string familyName; //player family name
		int rad; //player respawn area descriptor
		int rrd; //player respawn room descriptor
		int actionList[64]; //actions available to the player, in order that the player would likely use them
		int numActions;

		int md; //unique player descriptor
		string name; //player name
		int ad; //player area location descriptor
		int rd; //player room location descriptor

		Stat statList[16];

		bool valid;

	public:
		Player();

		Player(const int& m, const string& n, const int& ra, const int& rr, const char *filename, const bool& isPlayer = false);

		const int& getFamilyDescriptor() const;

		const string& getFamilyName() const;

		const int& getRespawnAreaDescriptor() const;

		const int& getRespawnRoomDescriptor() const;

		const int& getDescriptor() const;

		const string& getName() const;

		const int& getAreaDescriptor() const;

		const int& getRoomDescriptor() const;

		const pair<int, int> chooseAction(double input[]);

		Stat& getStat(int sd);

		Stat& getStat(string s);

		void setStat(int sd, int val);

		void setStat(string s, int val);

		const bool& isPlayer() const;

		const bool& isValid() const;

		void damage(int amount);

		const int requestOrganism(); //TODO burn to the ground

		void retireOrganism(double fitness); //TODO burn to the ground
};

#endif
