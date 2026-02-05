/*
 * Stat.h
 *
 *  Created on: Jan 2, 2010
 *      Author: kincho
 */

#ifndef STAT_H_
#define STAT_H_

#include <cstdlib>
#include <string>

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

using namespace std;
using namespace rapidxml;

#include "MasterStatMap.cpp"

class Stat
{
	private:
		int sd;  //stat descriptor
		int lvl; //this stat's level
		int initial; //starting point for this stat (for max value)
		int growth;  //growth per level (for max value)
		int current; //stat's current value

		int xpinitial; //xp required to level this stat
		int xpgrowth;  //requirement growth
		int xpcurrent; //current progress toward the next level

		bool valid;

	public:
		Stat();
		Stat(const int& level, const xml_node<> * const statRoot);
		virtual ~Stat();

		void setLevel(const int& level);
		const int getDescriptor() const;
		const int getCurrent() const;
		void setCurrent(const int& c);
		const int getMax() const;
		const int getXPCurrent() const;
		void setXPCurrent(const int& xp);
		const int getXPMax() const;
		bool isValid();
};

#endif /* STAT_H_ */
