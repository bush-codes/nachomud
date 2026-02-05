/*
 * Player.cpp
 *
 *  Created on: Sep 12, 2009
 *      Author: kincho
 */

#include <algorithm>
#include "Player.h"

#ifndef PLAYER_CPP
#define PLAYER_CPP

using namespace std;
using namespace rapidxml;

Player::Player() :
	valid(false)
{
}

Player::Player(const int& m, const string& n, const int& ra, const int& rr, const char *filename, const bool& isPlayer) :
	player(isPlayer), mfd(-1), rad(ra), rrd(rr), numActions(0), md(m), name(n), valid(true)
{
	file<> f(filename);
	xml_document<> doc;
	doc.parse<0> (f.data());
	const xml_node<> * const playerRoot = doc.first_node();

	mfd = atoi(playerRoot->first_attribute("mfd")->value());
	familyName = string(playerRoot->first_node("fname")->value());

	const xml_node<> * const locationNode = playerRoot->first_node("location");
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

	const xml_node<> * currentStat = playerRoot->first_node("stat");

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

	const xml_node<> * currentAction = playerRoot->first_node("action");
	numActions = 0;
	while(currentAction != NULL)
	{
		actionList[numActions] = atoi(currentAction->first_attribute("actid")->value());
		currentAction = currentAction->next_sibling("action");
		++numActions;
	}

	BrainFactory::Instance().addBrain(mfd, name, numActions);
}

const int& Player::getFamilyDescriptor() const
{
	return mfd;
}

const string& Player::getFamilyName() const
{
	return familyName;
}

const int& Player::getRespawnAreaDescriptor() const
{
	return rad;
}

const int& Player::getRespawnRoomDescriptor() const
{
	return rrd;
}

const int& Player::getDescriptor() const
{
	return md;
}

const string& Player::getName() const
{
	return name;
}

const int& Player::getAreaDescriptor() const
{
	return ad;
}

const int& Player::getRoomDescriptor() const
{
	return rd;
}

const pair<int, int> Player::chooseAction(double input[])
{
//	int numInputs = BrainFactory::Instance().getBrain(mfd).getNumInputs();
//	double input[numInputs];
//	for(int i = 0; i < numInputs; ++i)
//		input[i] = 0;
//	input[0] = getStat("hp").getCurrent();
//	input[1] = getStat("mp").getCurrent();

	pair<int, int> rawDecisionPair = BrainFactory::Instance().getBrain(mfd).chooseAction(input);

	//Must translate player brain's view of the action descriptor to the global view of the action descriptor
	//Targeting should remain the same
	return make_pair(actionList[rawDecisionPair.first], rawDecisionPair.second);
}

Stat& Player::getStat(int sd)
{
	return statList[sd];
}

Stat& Player::getStat(string s)
{
	return statList[MasterStatMap::Instance().getStatDescriptor(s)];
}

void Player::setStat(int sd, int val)
{
	statList[sd].setCurrent(val);
}

void Player::setStat(string s, int val)
{
	statList[MasterStatMap::Instance().getStatDescriptor(s)].setCurrent(val);
}

const bool& Player::isPlayer() const
{
	return player;
}

const bool& Player::isValid() const
{
	return valid;
}

void Player::damage(int amount) //This method needs die a horrible death
{
	setStat("hp", getStat("hp").getCurrent() - amount);
}

const int Player::requestOrganism()
{
	return BrainFactory::Instance().getBrain(mfd).requestOrganism();
}

void Player::retireOrganism(double fitness)
{
	BrainFactory::Instance().getBrain(mfd).retireOrganism(fitness);
}

#endif
