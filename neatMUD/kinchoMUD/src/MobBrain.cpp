/*
 * MobBrain.cpp
 *
 *  Created on: Oct 4, 2009
 *      Author: kincho
 */

#include "MobBrain.h"

#ifndef MOBBRAIN_CPP
#define MOBBRAIN_CPP

MobBrain::MobBrain()
{
}

MobBrain::MobBrain(const char *filename, int numActs) :
	orgd(-1), gen(NULL), pop(NULL), numActions(numActs),
	numStats(MasterStatMap::Instance().getNumStats()), numContainers(MasterStatMap::Instance().getNumContainers()),
	numBuffs(0)
{
	mobName = string(filename);

	string popName = "data/mobs/ai/" + mobName + ".pop";
	ifstream pFile(popName.c_str(),ios::in);
	if(pFile.is_open())
	{
		pop = new Population(popName.c_str());
	}
	else
	{
		string genomeName = "data/mobs/ai/" + mobName + ".genome";

		ifstream gFile(genomeName.c_str(), ios::in);

		if (gFile.is_open())
		{
			char curword[20];
			int id;

			gFile >> curword;
			gFile >> id;

			gen = new Genome(id, gFile);
		}
		else
		{
			gen = new Genome(0, getNumInputs(), getNumOutputs(), 1, 2 * (numActions + 10), true, .3);
			ofstream oFile(genomeName.c_str());
			gen->print_to_file(oFile);
		}
		gFile.close();

		pop = new Population(gen, NEAT::pop_size);
	}

	pop->verify();

	for (int i = 0; i < (int)pop->organisms.size(); ++i)
	{
		freeOrganisms.push_back(i);
		currentFitness.push_back(0);
	}
}

MobBrain::~MobBrain()
{
	delete gen;
	delete pop;
}

const int MobBrain::getNumInputs()
{
	return 1 + (10 * (1 + numContainers)) + numBuffs;
}

const int MobBrain::getNumOutputs()
{
	return numActions + 2;
}

const pair<int, int> MobBrain::chooseAction(double input[]) const
{
	int numNodes;

	if (orgd == -1)
	{
		return make_pair(0,0);
	}
	else
	{
		Network* net = pop->organisms[orgd]->net;
		numNodes = (net->outputs.size());

		net->load_sensors(input);
		net->activate();

		double maxOutput = (net->outputs[0])->activation;
		int maxDecisionIndex = 0;
		for(int k = 1; k < numActions; ++k)
		{
			double currentOutput = (net->outputs[k])->activation;
			if(currentOutput > maxOutput)
			{
				maxOutput = currentOutput;
				maxDecisionIndex = k;
			}
		}

		maxOutput = (net->outputs[numActions])->activation;
		int maxTargetIndex = 0;
		for(int k = numActions; k < numActions + 2; ++k)
		{
			double currentOutput = (net->outputs[k])->activation;
			if(currentOutput > maxOutput)
			{
				maxOutput = currentOutput;
				maxTargetIndex = k - numActions;
			}
		}

		return make_pair(maxDecisionIndex,maxTargetIndex);
	}
}

const int MobBrain::requestOrganism()
{
	if (freeOrganisms.size() == 0)
	{
		return -1;
	}

	else
	{
		orgd = freeOrganisms.back();

		freeOrganisms.pop_back();
		return orgd;
	}
}

void MobBrain::retireOrganism(double fitness)
{
	currentFitness[orgd] = fitness;

	vector<Organism*>::iterator curorg;

	int offspring_count;
	int num_species_target = NEAT::pop_size / 15;

	int compat_adjust_frequency = NEAT::pop_size / 10;
	if (compat_adjust_frequency < 1)
		compat_adjust_frequency = 1;

	Organism *new_org;

	if (orgd >= 0 && orgd < (int)pop->organisms.size())
	{
		pop->organisms[orgd]->fitness = fitness;
		pop->organisms[orgd]->time_alive++;

		doneOrganisms.push_back(orgd);
		//evaluate population
		if (doneOrganisms.size() == pop->organisms.size())
		{
			pop->rank_within_species();
			pop->estimate_all_averages();

			if (offspring_count % compat_adjust_frequency == 0)
			{
				int num_species = pop->species.size();
				double compat_mod = 0.1; //Modify compat thresh to control speciation

				// This tinkers with the compatibility threshold
				if (num_species < num_species_target)
				{
					NEAT::compat_threshold -= compat_mod;
				}
				else if (num_species > num_species_target)
					NEAT::compat_threshold += compat_mod;

				if (NEAT::compat_threshold < 0.3)
					NEAT::compat_threshold = 0.3;

				//Go through entire population, reassigning organisms to new species
				for (curorg = (pop->organisms).begin(); curorg != pop->organisms.end(); ++curorg)
				{
					pop->reassign_species(*curorg);
				}
			}

			//Remove the worst organism
			Organism* worstOrg = pop->remove_worst();

			//Here we call two rtNEAT calls:
			//1) choose_parent_species() decides which species should produce the next offspring
			//2) reproduce_one(...) creates a single offspring from the chosen species
			new_org = (pop->choose_parent_species())->reproduce_one(offspring_count, pop, pop->species);

			Console::Instance().displayln("Mobs have sex.");

			string fitnessFilename = "data/mobs/stat/" + mobName + ".stat";
			ofstream fitnessFile(fitnessFilename.c_str(), ios::app);
			for(int i = 0; i < (int)currentFitness.size(); ++i)
			{
				fitnessFile << currentFitness[i] << " ";
			}
			fitnessFile << "\r\n";
			fitnessFile.close();

			while (!doneOrganisms.empty())
			{
				int maxFitness = 0;
				int maxIndex = 0;

				for(int i = 0; i < (int)currentFitness.size(); ++i)
				{
					if(maxFitness < currentFitness[i])
					{
						maxFitness = currentFitness[i];
						maxIndex = i;
					}
				}

				currentFitness[maxIndex] = -1;
				freeOrganisms.push_back(maxIndex);
				doneOrganisms.pop_back();
			}

			currentFitness.clear();
			while(currentFitness.size()!=freeOrganisms.size())
				currentFitness.push_back(0);

			//Print current best genome to file
			string genomeName = "data/mobs/ai/" + mobName + ".genome";
			Organism* bestOrg = pop->organisms[freeOrganisms[0]];
			ofstream oFile(genomeName.c_str());
			bestOrg->gnome->print_to_file(oFile);
		}
	}
}

#endif
