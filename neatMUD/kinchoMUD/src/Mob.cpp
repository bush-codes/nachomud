/*
 * Mob.cpp
 *
 *  Created on: Sep 12, 2009
 *      Author: kincho
 */

#include <algorithm>
#include "Mob.h"

#ifndef MOB_CPP
#define MOB_CPP

using namespace std;
using namespace rapidxml;

Mob::Mob() :
	valid(false)
{
}

Mob::Mob(const int& m, const string& n, const int& ra, const int& rr, const char *filename, const bool& isPlayer) :
	player(isPlayer), mfd(-1), rad(ra), rrd(rr), numActions(0), md(m), name(n), valid(true)
{
	file<> f(filename);
	xml_document<> doc;
	doc.parse<0> (f.data());
	const xml_node<> * const mobRoot = doc.first_node();

	mfd = atoi(mobRoot->first_attribute("mfd")->value());
	familyName = string(mobRoot->first_node("fname")->value());

	const xml_node<> * const locationNode = mobRoot->first_node("location");
	if(locationNode != NULL)
	{
		ad = atoi(locationNode->first_attribute("ad")->value());
		rd = atoi(locationNode->first_attribute("rd")->value());
	}
	else
	{
		ad = rad;
		rd = rrd;
	}

	const xml_node<> * currentStat = mobRoot->first_node("stat");

	//First run by hand to determine level,
	Stat s(0, currentStat);
	statList[s.getDescriptor()] = s;
	statList[0].setLevel(statList[0].getCurrent());
	currentStat = currentStat->next_sibling("stat");

	while(currentStat != NULL)
	{
		Stat s(statList[0].getCurrent(), currentStat);
		statList[s.getDescriptor()] = s;
		currentStat = currentStat->next_sibling("stat");
	}

	const xml_node<> * currentAction = mobRoot->first_node("action");
	numActions = 0;
	while(currentAction != NULL)
	{
		actionList[numActions] = atoi(currentAction->first_attribute("actid")->value());
		currentAction = currentAction->next_sibling("action");
		++numActions;
	}

	BrainFactory::Instance().addBrain(mfd, name, numActions);
}

const int& Mob::getFamilyDescriptor() const
{
	return mfd;
}

const string& Mob::getFamilyName() const
{
	return familyName;
}

const int& Mob::getRespawnAreaDescriptor() const
{
	return rad;
}

const int& Mob::getRespawnRoomDescriptor() const
{
	return rrd;
}

const int& Mob::getDescriptor() const
{
	return md;
}

const string& Mob::getName() const
{
	return name;
}

const int& Mob::getAreaDescriptor() const
{
	return ad;
}

const int& Mob::getRoomDescriptor() const
{
	return rd;
}

const pair<int, int> Mob::chooseAction(double input[])
{
//	int numInputs = BrainFactory::Instance().getBrain(mfd).getNumInputs();
//	double input[numInputs];
//	for(int i = 0; i < numInputs; ++i)
//		input[i] = 0;
//	input[0] = getStat("hp").getCurrent();
//	input[1] = getStat("mp").getCurrent();

	pair<int, int> rawDecisionPair = BrainFactory::Instance().getBrain(mfd).chooseAction(input);

	//Must translate mob brain's view of the action descriptor to the global view of the action descriptor
	//Targeting should remain the same
	return make_pair(actionList[rawDecisionPair.first], rawDecisionPair.second);
}

Stat& Mob::getStat(int sd)
{
	return statList[sd];
}

Stat& Mob::getStat(string s)
{
	return statList[MasterStatMap::Instance().getStatDescriptor(s)];
}

void Mob::setStat(int sd, int val)
{
	statList[sd].setCurrent(val);
}

void Mob::setStat(string s, int val)
{
	statList[MasterStatMap::Instance().getStatDescriptor(s)].setCurrent(val);
}

const bool& Mob::isPlayer() const
{
	return player;
}

const bool& Mob::isValid() const
{
	return valid;
}

void Mob::damage(int amount) //This method needs die a horrible death
{
	setStat("hp", getStat("hp").getCurrent() - amount);
}

const int Mob::requestOrganism()
{
	return BrainFactory::Instance().getBrain(mfd).requestOrganism();
}

void Mob::retireOrganism(double fitness)
{
	BrainFactory::Instance().getBrain(mfd).retireOrganism(fitness);
}

#endif
