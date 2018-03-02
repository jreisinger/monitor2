#!/usr/bin/perl
use strict;
use warnings;
use File::Find;

@ARGV = qw(.) unless @ARGV;
my ($age, $name) = (-1, "");

sub youngest {
    return if not -f;
    return if $age > (stat(_))[9];
    $age = (stat(_))[9];
    $name = $File::Find::name;
}

find(\&youngest, @ARGV);
printf("%s --> %s\n", $name, scalar localtime $age);

