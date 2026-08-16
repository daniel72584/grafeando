import pytest
from parsers.typescript_parser import TypeScriptParser


def test_parse_nestjs_controller_and_service():
    parser = TypeScriptParser()
    code = b"""
import { Controller, Get, Injectable } from '@nestjs/common';

@Injectable()
export class CatsService {
  findAll() { return ['cat']; }
}

@Controller('cats')
export class CatsController {
  constructor(private readonly catsService: CatsService) {}

  @Get()
  getCats() {
    return this.catsService.findAll();
  }
}
"""
    res = parser.parse_file("cats.controller.ts", code)

    classes = {c["name"]: c["category"] for c in res["classes"]}
    assert classes["CatsService"] == "service"
    assert classes["CatsController"] == "controller"

    injects = [inj["target_class_name"] for inj in res["injects"]]
    assert "CatsService" in injects


def test_parse_react_components_and_jsx():
    parser = TypeScriptParser()
    code = b"""
import React from 'react';

export function Button() {
  return <button>Click</button>;
}

export function Header() {
  return (
    <header>
      <Button />
    </header>
  );
}
"""
    res = parser.parse_file("Header.tsx", code)

    func_categories = {f["name"]: f["category"] for f in res["functions"]}
    assert func_categories["Button"] == "component"
    assert func_categories["Header"] == "component"

    renders = [r["rendered_component_name"] for r in res["renders"]]
    assert "Button" in renders
