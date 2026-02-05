/*
 * Stat.cpp
 *
 *  Created on: Jan 2, 2010
 *      Author: kincho
 */

#include "Stat.h"

Stat::Stat() : valid(false), lvl(0)
{

}

Stat::Stat(const int& level, const xml_node<> * const statRoot) : valid(true), lvl(level)
{
	sd = atoi(statRoot->first_attribute("sd")->value());

	const xml_attribute<> * currentAttribute = statRoot->first_attribute("initial");
	initial = (currentAttribute != NULL) ? atoi(currentAttribute->value()) : 0;

	currentAttribute = statRoot->first_attribute("growth");
	growth = (currentAttribute != NULL) ? atoi(currentAttribute->value()) : 0;

	currentAttribute = statRoot->first_attribute("current");
	current = (currentAttribute != NULL) ? atoi(currentAttribute->value()) : initial + (growth * (lvl - 1));

	currentAttribute = statRoot->first_attribute("xpinitial");
	xpinitial = (currentAttribute != NULL) ? atoi(currentAttribute->value()) : 0;

	currentAttribute = statRoot->first_attribute("xpgrowth");
	xpgrowth = (currentAttribute != NULL) ? atoi(currentAttribute->value()) : 0;

	currentAttribute = statRoot->first_attribute("xpcurrent");
	xpcurrent = (currentAttribute != NULL) ? atoi(currentAttribute->value()) : 0;
}

Stat::~Stat()
{

}

void Stat::setLevel(const int& level)
{
	lvl = level;
}

const int Stat::getDescriptor() const
{
	return sd;
}

const int Stat::getCurrent() const
{
	if(MasterStatMap::Instance().isMatchedStat(sd))
	{
		return getMax();
	}
	else
	{
		return current;
	}
}

void Stat::setCurrent(const int& c)
{
	current = c;
}

const int Stat::getMax() const
{
	return initial + (growth * (lvl - 1));
}

const int Stat::getXPCurrent() const
{
	return xpcurrent;
}

void Stat::setXPCurrent(const int& xp)
{
	xpcurrent = xp;
}

const int Stat::getXPMax() const
{
	return xpinitial + (xpgrowth * (lvl - 1));
}

bool Stat::isValid()
{
	return valid;
}
