/*
 * MobBrain.cpp
 *
 *  Created on: Oct 4, 2009
 *      Author: kincho
 */

#ifndef MOBBRAIN_H
#define MOBBRAIN_H

#include <iostream>
#include <fstream>
#include <cstdlib>
#include <string>
#include <vector>
#include <utility>

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

#include "Direction.cpp"
#include "Action.cpp"
#include "MasterStatMap.cpp"
#include "Console.h"

//#include "rtNEAT.1.0/neat.h"
//#include "rtNEAT.1.0/network.h"
//#include "rtNEAT.1.0/population.h"
//#include "rtNEAT.1.0/organism.h"
//#include "rtNEAT.1.0/genome.h"
//#include "rtNEAT.1.0/species.h"

using namespace std;
using namespace rapidxml;
//using namespace NEAT;

class MobBrain
{
	private:
//		Genome* gen;
//		Population* pop;
		vector<int> freeOrganisms;
		vector<int> doneOrganisms;
		vector<double> currentFitness;
		string mobName;

		int orgd;
		int numActions;
		int numStats;
		int numContainers;
		int numBuffs;

	public:
		MobBrain();

		MobBrain(const char *filename, int numActions);

		virtual ~MobBrain();

		const int getNumInputs();

		const int getNumOutputs();

		const pair<int, int> chooseAction(double input[]) const;

		const int requestOrganism();

		void retireOrganism(double fitness);
};

#endif
