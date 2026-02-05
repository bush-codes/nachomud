/*
 * Console.cpp
 *
 *  Created on: Sep 8, 2009
 *      Author: kincho
 */

#ifndef CONSOLE_CPP
#define CONSOLE_CPP

#include "Console.h"

Console::Console() // Private constructor
{
	active = false;
}

Console& Console::Instance()
{
	static Console singleton;
	return singleton;
}

void Console::clear_screen()
{
	#ifdef WINDOWS
		std::system ( "CLS" );
	#else
		// Assume POSIX
		std::system( "clear" );
	#endif
}

void Console::display(string out)
{
	cout << out << flush;
}

void Console::newLine()
{
	cout << endl << flush;
}

void Console::displayln(string out)
{
	display(out);
	newLine();
}

void Console::displayInt(int out)
{
	cout << out << flush;
}

void Console::displayBool(bool out)
{
	cout << out << flush;
}

string Console::prompt(map<string, int> vals)
{
	cout << "< | " << flush;
	map<string, int>::iterator it;
	for(it = vals.begin(); it != vals.end(); it++)
	{
		cout << it->first + ": " << it->second << " | " << flush;
	}
	cout << "> " << flush;
	return prompt();
}

string Console::prompt()
{
	cout << "?: " << flush;
	string input;
	getline(std::cin, input, '\n');
	return input;
}

bool Console::isActive()
{
	return active;
}

void Console::start()
{
	active = true;
}

void Console::quit()
{
	active = false;
}

#endif
