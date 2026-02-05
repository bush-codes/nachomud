/*
 * Login.cpp
 *
 *  Created on: Aug 22, 2009
 *      Author: kincho
 */

#include "Login.h"

Login::Login() : valid(false) {}
Login::Login(const char *filename) : valid(true)
{
	file<> f(filename);
	xml_document<> doc;
	doc.parse<0> (f.data());
	const xml_node<> * const loginRoot = doc.first_node();

	md = atoi(loginRoot->first_attribute("md")->value());
	description = string(loginRoot->first_node("description")->value());
}

Login::~Login(){}

const int Login::getDescriptor() const
{
	return md;
}

const string Login::getDescription()
{
	return description;
}
