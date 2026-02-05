/*
 * Chain.cpp
 *
 *  Created on: Sep 8, 2009
 *      Author: kincho
 */

#ifndef CHAIN_CPP
#define CHAIN_CPP

#include "Area.cpp"
#include "Battle.cpp"
#include "Login.h"
#include <sstream>
#include <map>
#include <vector>
#include <stdlib.h>
#include <time.h>

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

class Chain
{
	private:
		Login lp;

		Area areaList[100];
		int numAreas;

		Mob mobList[100];
		int numMobs;
		map<string, int> mobMap;

		Action actionList[100]; //Action ID indexes into this array, maybe look into using a map later
		int numActions;
		map<string, int> commandMap;

		//TODO probably need to look into this, works for login for now.
		int currentPlayer;

		bool requestLogin(string playerName)
		{
			map<string, int>::iterator iter;
			bool foundMob = false;
			int myMobId = -1;

			for (iter = mobMap.begin(); iter != mobMap.end(); ++iter)
			{
				if (playerName == iter->first)
				{
					foundMob = true;
					myMobId = iter->second;
				}
			}
			//TODO KinchoError class
			try
			{
				getMob(myMobId);
			}

			catch (const char* str)
			{
				return false;
			}

			//Login Successful
			currentPlayer = myMobId;
			return true;
		}

		const bool requestAction(const int& actingMob, const int& requestedAction, const string actionFields[])
		{
			if (requestedAction == 0)
			{
				return requestLogin(actionFields[0]);
			}
			else if (requestedAction == 1)
			{
				Console::Instance().quit();
				return false;
			}
			else if (requestedAction == 2)
			{
//				requestMessage();
				return false;
			}
			else if (3 <= requestedAction && requestedAction <= 12)
			{
				Console::Instance().display(requestMove(actingMob, requestedAction));
				return true;
			}
			//look
			else if (requestedAction == 13)
			{
				Console::Instance().displayln(Chain::Instance().lookingGlass(actingMob));
				return true;
			}
			//open
			else if (requestedAction == 14)
			{
				Console::Instance().displayln(Chain::Instance().requestOpen(actingMob, actionFields[0]));
				return true;
			}
			//close
			else if (requestedAction == 15)
			{
				Console::Instance().displayln(Chain::Instance().requestClose(actingMob, actionFields[0]));
				return true;
			}
			else if (requestedAction == 19)
			{
				if(actionFields[0] == "0")
				{
					Battle::Instance().autoBattle(getMob(actingMob), getMob(mobMap[actionFields[1]]));
					return true;
				}
				else if(actionFields[0] == "1")
				{
					Battle::Instance().autoBattle2(getMob(actingMob), getMob(mobMap[actionFields[1]]));
					return true;
				}
				return false;
			}
			//TODO battle actions are a hack, mainly because battle code is a big hack
			else if (requestedAction == 20)
			{
				Battle::Instance().startBattle(getMob(actingMob), getMob(mobMap[actionFields[0]]));
				return true;
			}
			else if (requestedAction == 21)
			{
				//TODO hack for now
				getMob(actingMob).setStat("hp", getMob(actingMob).getStat("hp").getMax());
				getMob(actingMob).setStat("mp", getMob(actingMob).getStat("mp").getCurrent() - 1);
				return true;
			}
			else if (requestedAction == 22)
			{
				Battle::Instance().startBattle(getMob(actingMob), getMob(mobMap[actionFields[0]]));
				return true;
			}
			else if (requestedAction == 23)
			{
				Battle::Instance().startBattle(getMob(actingMob), getMob(mobMap[actionFields[0]]));
				return true;
			}
			else if (requestedAction == 24)
			{
				Battle::Instance().startBattle(getMob(actingMob), getMob(mobMap[actionFields[0]]));
				return true;
			}
			else if (requestedAction == 25)
			{
				Console::Instance().displayln("Nothing to do!");
				return true;
			}
			return false;
		}

		string lookingGlass(const int& mobId)
		{
			string ret = "\r\n";

			Mob& mob = getMob(mobId);
			int mobArea = mob.getAreaDescriptor();
			int mobRoom = mob.getRoomDescriptor();
			ret += getArea(mobArea).getRoom(mobRoom).toString();
			for (int i = 0; i < Chain::Instance().getNumMobs(); ++i)
			{
				Mob& curMob = getMob(i);
				if (curMob.getRoomDescriptor() == mobRoom && curMob.getDescriptor() != mobId && curMob.getStat("hp").getCurrent() > 0)
				{
					string name = curMob.isPlayer() ? curMob.getName() : curMob.getFamilyName();
					char first = tolower(name[0]);
					string front = (first == 'a' || first == 'e' || first == 'i' || first == 'o' || first == 'u' || first == 'y') ? "An " : "A ";

					ret += front + name + " is in the room.\r\n";
				}
			}

			return ret;
		}

		//TODO TODO TODO FIXME mobs should NOT keep track of where they are, we should do that here.
		//TODO TODO TODO FIXME wai? - kink
		const string requestMove(const int& actingMob, const int& requestedDirection)
		{
			Mob& mob = mobList[actingMob];
			Action& action = actionList[requestedDirection];

			//return true on successful action
			Exit &e = Chain::Instance().getArea(mob.getAreaDescriptor()).getRoom(mob.getRoomDescriptor()).getExit(string2Direction(action.getName()));
			//If the mob and exit are valid
			if (mob.isValid() && e.isValid())
			{
				//And the exit has no door or is otherwise open
				if(!e.hasDoor() || getArea(e.getAreaDescriptor()).getDoor(e.getDoorDescriptor()).isOpen())
				{
					mob.ad = e.getAreaDescriptor();
					mob.rd = e.getRoomDescriptor();

					return "You move " + action.getName() + ".\r\n" + Chain::Instance().lookingGlass(actingMob);
				}

				//We just ran into a door.  Oww.
				return "A door impedes your way.\r\n";
			}

			//We failed to move.  Derp.
			return "You cannot move in that direction.\r\n";
		}

		string requestOpen(const int& mobId, const string& directionString)
		{
			string result = "";

			int ad = Chain::Instance().getMob(mobId).getAreaDescriptor();
			int rd = Chain::Instance().getMob(mobId).getRoomDescriptor();

			int directionNum = string2DirectionDescriptor(directionString);

			if(directionNum > -1)
			{
				Direction dir = directionArray[directionNum];
				Exit& e = Chain::Instance().getArea(ad).getRoom(rd).getExit(dir);

				if(e.hasDoor())
				{
					Door& d = Chain::Instance().getArea(ad).getDoor(e.getDoorDescriptor());

					result = d.isOpen() ? "" : "You open the door.";
					d.open();
				}
			}
			else
				result = directionString + " is an invalid direction.";

			return result;
		}

		string requestClose(const int& mobId, const string& directionString)
		{
			string result = "";

			int ad = Chain::Instance().getMob(mobId).getAreaDescriptor();
			int rd = Chain::Instance().getMob(mobId).getRoomDescriptor();

			int directionNum = string2DirectionDescriptor(directionString);

			if(directionNum > -1)
			{
				Direction dir = directionArray[directionNum];
				Exit& e = Chain::Instance().getArea(ad).getRoom(rd).getExit(dir);

				if(e.hasDoor())
				{
					Door& d = Chain::Instance().getArea(ad).getDoor(e.getDoorDescriptor());

					result = d.isClosed() ? "" : "You close the door.";
					d.close();
				}
			}
			else
				result = directionString + " is an invalid direction.";

			return result;
		}

		Chain() // Private constructor
		{
			srand ( time(NULL));
//			NEAT::load_neat_params("data/params.neat");
			//Login Page
			lp = Login("data/master.login"); //TODO loginpage, use <p> elements

			//Areas
			file<> areaFile("data/master.area");
			xml_document<> areaDoc;
			areaDoc.parse<0> (areaFile.data());
			const xml_node<> * const areaRoot = areaDoc.first_node();
			const xml_node<> * currentArea = areaRoot->first_node("file");
			numAreas = 0;
			while (currentArea != NULL)
			{
				string curPath = string(currentArea->first_attribute("path")->value());
				areaList[numAreas] = Area(curPath.c_str());
				++numAreas;
				currentArea = currentArea->next_sibling("file");

				//Area Mobs
				file<> mobFile(string(curPath + ".mobs").c_str());
				xml_document<> mobDoc;
				mobDoc.parse<0> (mobFile.data());
				const xml_node<> * const mobRoot = mobDoc.first_node();
				const xml_node<> * currentMob = mobRoot;
				numMobs = 0;
				while (currentMob != NULL)
				{
					string mobName = string(currentMob->first_attribute("name")->value());
					int rad = atoi(currentMob->first_attribute("rad")->value());
					int rrd = atoi(currentMob->first_attribute("rrd")->value());
					string mobPath = string(currentMob->first_attribute("path")->value());
					mobList[numMobs] = Mob(numMobs, mobName, rad, rrd, mobPath.c_str());
					++numMobs;
					currentMob = currentMob->next_sibling("mob");
				}
			}

			//Player Mobs
			//The difference here is purely whether we add to the mob map or not, since multiple mobs may share the same name and players may not
			file<> mobFile("data/master.pc");
			xml_document<> mobDoc;
			mobDoc.parse<0> (mobFile.data());
			const xml_node<> * const mobRoot = mobDoc.first_node();
			const xml_node<> * currentMob = mobRoot;
			while (currentMob != NULL)
			{
				string mobName = string(currentMob->first_attribute("name")->value());
				int rad = atoi(currentMob->first_attribute("rad")->value());
				int rrd = atoi(currentMob->first_attribute("rrd")->value());
				string mobPath = string(currentMob->first_attribute("path")->value());
				mobList[numMobs] = Mob(numMobs, mobName, rad, rrd, mobPath.c_str());
				mobMap.insert(make_pair(mobList[numMobs].getName(), mobList[numMobs].getDescriptor()));
				++numMobs;
				currentMob = currentMob->next_sibling("mob");
			}

			//Commands
			file<> cmdFile("data/master.command");
			xml_document<> cmdDoc;
			cmdDoc.parse<0> (cmdFile.data());
			const xml_node<> * const cmdRoot = cmdDoc.first_node();
			const xml_node<> * currentCmd = cmdRoot->first_node("command");
			while (currentCmd != NULL)
			{
				string curCmdString = string(currentCmd->first_attribute("cmd")->value());
				commandMap.insert(make_pair(curCmdString, atoi(currentCmd->first_attribute("ad")->value())));
				currentCmd = currentCmd->next_sibling("command");
			}

			//Actions
			file<> actFile("data/master.action");
			xml_document<> actDoc;
			actDoc.parse<0> (actFile.data());
			const xml_node<> * const actRoot = actDoc.first_node();
			const xml_node<> * currentAct = actRoot->first_node("action");
			numActions = 0;
			while (currentAct != NULL)
			{
				int ad = atoi(currentAct->first_attribute("ad")->value());
				int numFields = atoi(currentAct->first_node("numfields")->value());
				string description = string(currentAct->first_node("description")->value());
				string name = string(currentAct->first_node("name")->value());
				actionList[ad] = Action(ad, name, description, numFields);
				++numActions;
				currentAct = currentAct->next_sibling("action");
			}
		}
		Chain(const Chain&); // Prevent copy-construction
		Chain& operator=(const Chain&); // Prevent assignment

	public:
		static Chain& Instance()
		{
			static Chain singleton;
			return singleton;
		}

		Area& getArea(const int& a)
		{
			if ((a < 0) || (a >= numAreas))
				throw "getArea(): index out of bounds\n";
			return areaList[a];
		}

		int& getNumAreas()
		{
			return numAreas;
		}

		Mob& getMob(const int& m)
		{
			if ((m < 0) || (m >= numMobs))
			{
				throw "getMob(): index out of bounds\n";
			}
			return mobList[m];
		}

		const int& getNumMobs() const
		{
			return numMobs;
		}

		const Action& getAction(const int& a) const
		{
			if ((a < 0) || (a >= numActions))
			{
				throw "getAction: index out of bounds\n";
			}
			return actionList[a];
		}

		const int& getNumActions() const
		{
			return numActions;
		}

		const int& getCurrentPlayer() const
		{
			return currentPlayer;
		}

		bool request(const int& actingMob, string command)
		{
			for (int k = 0; k < command.size(); ++k)
				command[k] = tolower(command[k]);

			vector<string> parsedCmd;
			string buf;
			stringstream ss(command);
			while (ss >> buf)
				parsedCmd.push_back(buf);

			map<string, int>::iterator iter;
			bool foundCmd = false;
			int ad = 0; //By default, ad(0) = Do Nothing

			//Pull action out of command
			for (iter = commandMap.begin(); iter != commandMap.end() && !foundCmd; ++iter)
			{
				if (parsedCmd[0] == iter->first)
				{
					foundCmd = true;
					ad = iter->second;
				}
			}

			//if number of fields is not properly filled out, do nothing
			if(parsedCmd.size() != getAction(ad).getNumFields() + 1)
			{
				ad = 0;
			}

			//Pull out all action fields to send to requestAction
			string actionFields[getAction(ad).getNumFields()];
			for(int k = 0; k < getAction(ad).getNumFields(); ++k)
			{
				actionFields[k] = parsedCmd[k + 1];
			}
			return requestAction(actingMob, ad, actionFields);
		}

		bool request(string command)
		{
			return request(-1, command);
		}
};

#endif
